from __future__ import annotations

import re
import unicodedata
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any, Callable, Protocol

from auto_check.engine.matching import find_valuation_matches
from auto_check.engine.models import (
    DifferenceDetail,
    PactAssetRow,
    ProjectBalance,
    ReconcileResult,
    ValuationMatch,
    ValuationRow,
)
from auto_check.engine.money import amounts_equal, to_decimal

"""
自动对数核心规则备注。

主表 zf_detail_2024 中仅处理 a0001 - d0000 不为 0 的项目。
处理顺序不能随意调整：
1. 先用估值表 0004 资产合计判断 zf_detail 的 a0001 是否正确。
2. 如果 a0001 与估值表资产不一致，只在估值表 1 开头最末级科目和 3001.XX 正数共同类科目中找差异原因。
3. 如果 a0001 与估值表资产一致，说明资产端正确，继续排查负债及权益端。
4. 负债及权益端先看 c1000 与 FA 4001；仍不能解释时，再查估值表非 1 开头科目。
5. 所有金额均精确比较，不允许误差。
"""


DISPLAY_CANDIDATE_GROUP_LIMIT = 5
ASSET_AM_CONFIRM_CANDIDATE_GROUP_LIMIT = 200
JIANGSU_TRUST_TEXT = "\u6c5f\u82cf\u4fe1\u6258"
CHINESE_PAREN_RE = re.compile(r"\uff08[^\uff08\uff09]*\uff09")
COMMON_RECEIVABLE_ASSET_TYPE = "应收账款_共同类"
COMMON_PAYABLE_ACCOUNT_TYPE = "应付账款_共同类"
SECURITY_BALANCE_TABLE_LABEL = "DM FA 证券余额表"
DM_PROJECT_INVEST_TABLE_LABEL = "DM AM 投融资余额表"
DM_SPV_PROJECT_INVEST_TABLE_LABEL = "DM AM SPV 投融资余额表"
PROPERTY_RIGHT_CONTRACT_TABLE_LABEL = "财产权合同信息表"


class ReconcileRepository(Protocol):
    def list_project_balances(self, date: str) -> list[ProjectBalance]: ...

    def get_fa_4001_balance(self, project_code: str, date: str) -> Decimal: ...

    def get_ta_assetshare_sum(self, project_code: str, date: str) -> Decimal: ...

    def get_valuation_asset_total(self, project_code: str, date: str) -> Decimal | None: ...

    def list_valuation_leaf_rows(
        self,
        project_code: str,
        date: str,
        account_prefix: str | None = None,
    ) -> list[ValuationRow]: ...

    def list_valuation_rows(
        self,
        project_code: str,
        date: str,
        account_prefix: str | None = None,
        exclude_prefix: str | None = None,
        leaf_only: bool = True,
    ) -> list[ValuationRow]: ...

    def list_pact_assets(
        self,
        project_code: str,
        date: str,
        asset_name: str,
    ) -> list[PactAssetRow]: ...

    def list_project_pact_assets(self, project_code: str, date: str) -> list[PactAssetRow]: ...

    def get_project_invest_balance(self, project_code: str, date: str, pact_id: str) -> Decimal | None: ...

    def get_ta_balance_totals(self, project_code: str, date: str) -> tuple[Decimal, Decimal]: ...

    def list_blank_ta_client_type_rows(self, project_code: str, date: str) -> list[dict[str, Any]]: ...

    def get_security_balance_refinement(
        self,
        project_code: str,
        date: str,
        stock_code: str,
        security_name: str,
    ) -> dict[str, Any] | None: ...

    def list_security_balance_amounts(self, project_code: str, date: str) -> list[dict[str, Any]]: ...

    def get_dm_project_invest_refinement(self, project_code: str, date: str, pact_id: str) -> dict[str, Any] | None: ...

    def get_dm_project_invest_contract_balance(self, project_code: str, date: str, pact_id: str) -> dict[str, Any] | None: ...

    def get_spv_project_invest_refinement(self, project_code: str, date: str, pact_id: str) -> dict[str, Any] | None: ...

    def get_property_right_refinement(self, project_code: str, pact_id: str) -> dict[str, Any] | None: ...

    def has_report_rows(self, table_parts: tuple[str, ...], date: str) -> bool: ...

    def count_report_project_name_matches_without_chinese_parentheses(self, date: str, normalized_name: str) -> int: ...

    def has_reverse_repo_blank_rows(self, project_code: str) -> bool: ...

    def get_reverse_repo_business_amount(self, project_code: str) -> Decimal: ...

    def get_positive_repo_business_amount(self, project_code: str) -> Decimal: ...


class RunCancelled(Exception):
    """Raised when a running reconciliation job is cancelled by the UI."""


class NoSourceReportData(Exception):
    """Raised when the source report table has no rows for the selected date."""

    def __init__(self, date: str):
        self.date = date
        super().__init__(f"报表对应日期无数据：{date}")


class ReconcileEngine:
    def __init__(
        self,
        repository: ReconcileRepository,
        *,
        max_combination_rows: int = 50,
        progress_logger: Callable[[str, int | None, str | None], None] | None = None,
        cancel_event: Any | None = None,
    ):
        self.repository = repository
        self.max_combination_rows = max_combination_rows
        self.progress_logger = progress_logger
        self.cancel_event = cancel_event

    def run(self, date: str) -> list[ReconcileResult]:
        results = []
        self._log("开始读取主表差异项目", 5, "读取数据")
        projects = self.repository.list_project_balances(date)
        self._check_cancelled()
        if not projects:
            self._log(f"报表对应日期无数据：{date}", 95, "生成报告")
            raise NoSourceReportData(date)
        pending_projects = [project for project in projects if not amounts_equal(project.difference, Decimal("0"))]
        self._log(
            f"读取完成：共 {len(projects)} 个项目，主差异非 0 的项目 {len(pending_projects)} 个",
            20,
            "验证数据完整性",
        )
        total = len(pending_projects)
        for index, project in enumerate(pending_projects, start=1):
            self._check_cancelled()
            progress = 20 + int(index * 65 / max(total, 1))
            self._log(
                f"分析项目 {index}/{total}：{project.project_code} {project.project_name}",
                progress,
                "自动分析差异",
            )
            # 主差异为 0 的项目无需展示；页面只关注资产合计与负债及权益合计不平的项目。
            results.append(self._reconcile_project(project, date))
        self._log(f"生成核对结果：{len(results)} 条差异", 95, "生成报告")
        return results

    def _check_cancelled(self) -> None:
        if self.cancel_event is not None and self.cancel_event.is_set():
            self._log("执行已被用户终止", None, None)
            raise RunCancelled("执行已终止")

    def _log(self, message: str, progress: int | None = None, step: str | None = None) -> None:
        if self.progress_logger is not None:
            self.progress_logger(message, progress, step)

    def _project_log(self, project: ProjectBalance, message: str, step: str | None = None) -> None:
        self._log(f"{project.project_code}：{message}", None, step)

    def _reconcile_project(self, project: ProjectBalance, date: str) -> ReconcileResult:
        self._check_cancelled()
        # 第一优先级：用估值表 0004 资产合计校验 zf_detail.a0001。
        # 只要资产合计不一致，就先走资产缺失/资产重复判断，不继续判断 c1000。
        self._project_log(project, "读取估值表0004资产合计", "校验资产合计")
        valuation_asset_total = self.repository.get_valuation_asset_total(project.project_code, date)
        self._check_cancelled()
        if valuation_asset_total is None:
            self._project_log(project, "估值表未找到0004资产合计，返回暂无法确定", "校验资产合计")
            return self._unknown_result(
                project,
                [
                    DifferenceDetail(
                        kind="unknown",
                        data={"basis": "估值表未找到 0004 资产合计，无法判断 a0001 是否正确。"},
                    )
                ],
                valuation_asset_total=None,
            )

        if not amounts_equal(project.asset_total, valuation_asset_total):
            self._project_log(
                project,
                f"资产合计不一致，zf_detail={project.asset_total}，估值表0004={valuation_asset_total}，进入资产端规则",
                "资产端分析",
            )
            return self._reconcile_asset_total_gap(project, date, valuation_asset_total)

        # 只有 a0001 与估值表 0004 一致时，才认为资产端正确，开始排查负债及权益端。
        self._project_log(project, "资产合计一致，读取FA 4001科目余额", "负债权益分析")
        fa4001 = self.repository.get_fa_4001_balance(project.project_code, date)
        self._check_cancelled()
        return self._reconcile_liability_equity_gap(project, date, fa4001, valuation_asset_total)

    def _reconcile_asset_total_gap(
        self,
        project: ProjectBalance,
        date: str,
        valuation_asset_total: Decimal,
    ) -> ReconcileResult:
        self._check_cancelled()
        # a0001 小于估值表资产：zf_detail 少记资产，预估为“资产缺失”。
        # a0001 大于估值表资产：zf_detail 多记资产，预估为“资产重复”。
        asset_gap = abs(project.asset_total - valuation_asset_total)
        expected_reason = "资产缺失" if project.asset_total < valuation_asset_total else "资产重复"
        self._project_log(project, f"资产端预估方向={expected_reason}，资产差异金额={asset_gap}", "资产端分析")

        # 资产端查估值表 1 开头的实际末级科目，以及 3001.XX 正数共同类资产。
        # AM 标的复核仍在后续步骤用四级科目判断是否进入复核。
        self._project_log(project, "读取估值表资产端候选科目", "读取估值表科目")
        valuation_rows = self.repository.list_valuation_rows(
            project.project_code,
            date,
            leaf_only=False,
        )
        self._check_cancelled()
        valuation_rows = _asset_gap_candidate_rows(valuation_rows)
        self._project_log(project, f"估值表资产端候选科目 {len(valuation_rows)} 行", "读取估值表科目")

        # 匹配金额使用绝对差额，因为这里已经通过大小关系确定了缺失或重复方向。
        self._project_log(project, f"匹配估值表资产端候选科目金额，目标={asset_gap}，候选={len(valuation_rows)} 行", "金额匹配")
        valuation_match = find_valuation_matches(
            valuation_rows,
            asset_gap,
            max_combination_rows=self.max_combination_rows,
            detect_ambiguous_combinations=True,
            max_ambiguous_groups=ASSET_AM_CONFIRM_CANDIDATE_GROUP_LIMIT,
            cancel_checker=self._check_cancelled,
        )
        bond_overflow_groups: set[str] = set()
        if valuation_match.match_type == "combination_overflow":
            valuation_match, bond_overflow_groups = self._find_natural_group_match(
                valuation_rows,
                asset_gap,
                detect_ambiguous_combinations=True,
                max_ambiguous_groups=ASSET_AM_CONFIRM_CANDIDATE_GROUP_LIMIT,
            )
        self._check_cancelled()
        self._project_log(
            project,
            f"估值表资产端候选科目匹配结果={valuation_match.match_type}，命中金额={valuation_match.total}{'，' + valuation_match.message if valuation_match.message else ''}",
            "金额匹配",
        )
        details = [
            DifferenceDetail(
                kind="asset_gap",
                data=_with_asset_type_specific_reason(
                    {
                        "reason": expected_reason,
                        "zf_asset_total": str(project.asset_total),
                        "valuation_asset_total": str(valuation_asset_total),
                        "asset_gap": str(asset_gap),
                        "match_type": valuation_match.match_type,
                        "match_total": str(valuation_match.total),
                        "match_message": valuation_match.message,
                        "account_scope": "1开头末级科目及3001.XX正数共同类资产",
                    },
                    expected_reason,
                    valuation_match.rows,
                ),
            )
        ]

        if valuation_match.match_type == "ambiguous_combination":
            details[0].data["candidate_groups"] = _candidate_groups_payload(valuation_match.candidate_groups)
            if expected_reason == "资产缺失":
                confirmed_match, confirmed_details = self._confirm_ambiguous_asset_missing_by_am(
                    project,
                    date,
                    valuation_match,
                    asset_gap,
                )
                if confirmed_match is not None:
                    details[0].data.update(
                        {
                            "match_type": confirmed_match.match_type,
                            "match_total": str(confirmed_match.total),
                            "match_message": confirmed_match.message,
                        }
                    )
                    _with_asset_type_specific_reason(details[0].data, expected_reason, confirmed_match.rows)
                    details.extend(confirmed_details)
                    details.append(self._asset_missing_refinement_detail(project, date, confirmed_match.rows))
                    return self._result(
                        project,
                        difference_reason=expected_reason,
                        match_status="已解释",
                        details=details,
                        valuation_match=confirmed_match,
                    )
            details[0].data["specific_reason"] = "候选不唯一"
            return self._result(
                project,
                difference_reason=f"{expected_reason} + 暂无法确定",
                match_status="候选不唯一",
                details=details,
                valuation_match=valuation_match,
            )

        if self._is_resolved(valuation_match):
            final_reason = expected_reason
            if expected_reason == "资产缺失":
                self._project_log(project, "资产缺失已命中，检查是否进入AM标的复核", "AM标的复核")
                am_result = self._find_asset_missing_am_reason(project, date, valuation_match.rows)
                if am_result is not None:
                    _specific_reason, am_detail = am_result
                    details.append(am_detail)
                details.append(self._asset_missing_refinement_detail(project, date, valuation_match.rows))
            elif expected_reason == "资产重复":
                details.append(self._asset_duplicate_refinement_detail(project, date, valuation_match.rows))
            return self._result(
                project,
                difference_reason=final_reason,
                match_status="已解释",
                details=details,
                valuation_match=valuation_match,
            )

        self._project_log(project, "资产端无法直接命中具体资产，返回资产差异", "资产端分析")
        asset_total_gap = project.asset_total - valuation_asset_total
        asset_difference_detail = self._asset_difference_refinement_detail(
            project,
            date,
            valuation_rows,
            asset_total_gap,
            bond_overflow_groups,
        )
        details.append(asset_difference_detail)
        if asset_difference_detail.data.get("is_full_match"):
            remaining_difference = project.difference - asset_total_gap
            asset_difference_detail.data["remaining_difference"] = str(remaining_difference)
            if amounts_equal(remaining_difference, Decimal("0")):
                return self._result(
                    project,
                    difference_reason="资产差异",
                    match_status="已解释",
                    details=details,
                    valuation_match=valuation_match,
                )

            self._project_log(
                project,
                f"资产差异已解释，资产修正后剩余差额={remaining_difference}，继续进入实收/负债权益链路",
                "资产差异后续核对",
            )
            fa4001 = self.repository.get_fa_4001_balance(project.project_code, date)
            adjusted_project = ProjectBalance(
                project.project_code,
                project.project_name,
                valuation_asset_total,
                project.liability_equity_total,
                project.received_trust_balance,
            )
            followup_result = self._reconcile_liability_equity_gap(
                adjusted_project,
                date,
                fa4001,
                valuation_asset_total,
                detect_main_difference_ambiguity=False,
            )
            next_index = len(asset_difference_detail.data.get("rows") or []) + 1
            followup_details = _shift_detail_indices(followup_result.details, next_index)
            asset_reason = str(asset_difference_detail.data.get("specific_reason") or "")
            followup_reason = _last_specific_reason(followup_details)
            if asset_reason and followup_reason:
                followup_reason = _ensure_reason_index(followup_reason, next_index)
                _set_last_specific_reason(
                    followup_details,
                    _renumber_specific_reason(f"{asset_reason}\n{followup_reason}"),
                )
            return self._result(
                project,
                difference_reason=f"资产差异 + {_followup_difference_reason(followup_result)}",
                match_status=followup_result.match_status,
                details=details + followup_details,
                valuation_match=followup_result.valuation_match,
                valuation_asset_total=valuation_asset_total,
            )

        match_status = self._status_for_match(valuation_match)
        return self._result(
            project,
            difference_reason="资产差异",
            match_status=match_status,
            details=details,
            valuation_match=valuation_match,
        )

    def _asset_difference_refinement_detail(
        self,
        project: ProjectBalance,
        date: str,
        valuation_rows: list[ValuationRow],
        asset_total_gap: Decimal,
        bond_overflow_groups: set[str] | None = None,
    ) -> DifferenceDetail:
        detail_rows = []
        market_total = Decimal("0")
        invest_total = Decimal("0")
        bond_rows = self._bond_security_balance_difference_rows(project, date, valuation_rows, bond_overflow_groups or set())
        for row in bond_rows:
            market_total += Decimal(row["market_value"])
            invest_total += Decimal(row["project_invest_balance"])
            row["index"] = _circled_index(len(detail_rows) + 1)
            detail_rows.append(row)

        for row in valuation_rows:
            self._check_cancelled()
            contract_type = _asset_difference_contract_type(row)
            if contract_type is None:
                continue

            pact_id = row.account_tail_code
            self._project_log(project, f"查询{contract_type}投融资余额，合同{pact_id}，估值金额={row.market_value}", "资产差异合同核对")
            if contract_type == "贷款合同":
                dm_row = self.repository.get_dm_project_invest_contract_balance(project.project_code, date, pact_id)
                invest_balance = None if dm_row is None else to_decimal(dm_row.get("pin_acbalance"))
                check_table = "dm.am_projinvest_zgxg_dm"
            else:
                invest_balance = self.repository.get_project_invest_balance(project.project_code, date, pact_id)
                check_table = "am_projinvest_dws"
            self._check_cancelled()
            if invest_balance is None:
                self._project_log(project, f"合同{pact_id}未找到AM投融资余额，跳过资产差异合同核对", "资产差异合同核对")
                continue
            row_difference = invest_balance - row.market_value
            self._project_log(project, f"合同{pact_id}：AM余额={invest_balance}，估值={row.market_value}，差异={row_difference}", "资产差异合同核对")
            if amounts_equal(row_difference, Decimal("0")):
                continue
            contract_label = _asset_difference_contract_label(row.account_name or pact_id, contract_type)
            market_total += row.market_value
            invest_total += invest_balance
            detail_rows.append(
                {
                    "index": _circled_index(len(detail_rows) + 1),
                    "asset_type": contract_type,
                    "asset_name": row.account_name or pact_id,
                    "account_code": row.account_code,
                    "account_name": row.account_name,
                    "pact_id": pact_id,
                    "market_value": str(row.market_value),
                    "project_invest_balance": str(invest_balance),
                    "difference": str(row_difference),
                    "check_table": check_table,
                    "reason": f"{contract_label}：FA科目余额与AM投融资余额有差异，差异值{row_difference}",
                }
            )

        reverse_repo_rows = [row for row in valuation_rows if _is_reverse_repo_account(row.account_code)]
        reverse_repo_market_total = _valuation_market_total(reverse_repo_rows)
        reverse_repo_business_amount = self.repository.get_reverse_repo_business_amount(project.project_code)
        reverse_repo_difference = reverse_repo_business_amount - reverse_repo_market_total
        if not amounts_equal(reverse_repo_difference, Decimal("0")):
            self._project_log(
                project,
                f"逆回购：存续回购业务表金额={reverse_repo_business_amount}，估值={reverse_repo_market_total}，差异={reverse_repo_difference}",
                "资产差异回购核对",
            )
            market_total += reverse_repo_market_total
            invest_total += reverse_repo_business_amount
            detail_rows.append(
                {
                    "index": _circled_index(len(detail_rows) + 1),
                    "asset_type": "逆回购",
                    "asset_name": "逆回购",
                    "account_code": _repo_account_code(reverse_repo_rows, "1111"),
                    "account_name": _repo_account_name(reverse_repo_rows, "逆回购"),
                    "pact_id": "",
                    "market_value": str(reverse_repo_market_total),
                    "project_invest_balance": str(reverse_repo_business_amount),
                    "difference": str(reverse_repo_difference),
                    "check_table": "ass_man_reg.ex_pledge_back",
                    "reason": f"逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值{reverse_repo_difference}",
                }
            )

        difference_total = invest_total - market_total
        is_full_match = bool(detail_rows) and amounts_equal(difference_total, asset_total_gap)
        if is_full_match:
            specific_reason = _asset_difference_full_reason(detail_rows)
        elif not amounts_equal(difference_total, Decimal("0")):
            specific_reason = _asset_difference_partial_reason(detail_rows, difference_total)
        else:
            specific_reason = "暂不明确具体资产差异"

        return DifferenceDetail(
            kind="asset_difference_refinement",
            data={
                "market_total": str(market_total),
                "project_invest_total": str(invest_total),
                "difference_total": str(difference_total),
                "asset_total_gap": str(asset_total_gap),
                "specific_reason": specific_reason,
                "is_full_match": is_full_match,
                "basis": "债券比较 DM证券余额 - FA债券本金科目余额；贷款、财产权合同分别比较 AM投融资余额 - FA科目余额；逆回购比较存续回购业务表金额 - FA科目余额；差异合计与 a0001-估值表0004 同方向且相等时视为完整解释。",
                "rows": detail_rows,
            },
        )

    def _reconcile_liability_equity_gap(
        self,
        project: ProjectBalance,
        date: str,
        fa4001: Decimal,
        valuation_asset_total: Decimal,
        *,
        detect_main_difference_ambiguity: bool = True,
    ) -> ReconcileResult:
        self._check_cancelled()
        # 资产端已确认正确后，先判断实收本金：
        # 整笔 4001 命中归为缺失/重复；4001-c1000 命中归为实收本金差异。
        if amounts_equal(project.difference, fa4001) and amounts_equal(project.received_trust_balance, Decimal("0")):
            return self._received_trust_whole_principal_result(
                project,
                date,
                fa4001,
                "实收本金缺失",
                valuation_asset_total,
            )
        received_trust_duplicate_count = _received_trust_duplicate_count(
            fa4001,
            project.received_trust_balance,
            project.difference,
        )
        if received_trust_duplicate_count is not None:
            return self._received_trust_whole_principal_result(
                project,
                date,
                fa4001,
                "实收本金重复",
                valuation_asset_total,
                repeat_count=received_trust_duplicate_count,
            )

        received_trust_difference = fa4001 - project.received_trust_balance
        self._project_log(
            project,
            f"核对实收信托，c1000={project.received_trust_balance}，FA4001={fa4001}，差异={received_trust_difference}",
            "实收信托核对",
        )
        if not amounts_equal(project.received_trust_balance, fa4001) and amounts_equal(
            received_trust_difference,
            project.difference,
        ):
            return self._received_trust_result(project, date, fa4001, received_trust_difference, valuation_asset_total)

        match_difference = project.difference
        detail_prefix: list[DifferenceDetail] = []
        residual_difference: Decimal | None = None
        if not amounts_equal(project.received_trust_balance, fa4001):
            residual_difference = project.difference - received_trust_difference
            match_difference = residual_difference
            detail_prefix.append(
                DifferenceDetail(
                    kind="received_trust",
                    data={
                        "c1000_balance": str(project.received_trust_balance),
                        "fa_4001_balance": str(fa4001),
                        "received_trust_difference": str(received_trust_difference),
                        "valuation_asset_total": str(valuation_asset_total),
                        "specific_reason": _received_trust_difference_reason(received_trust_difference),
                        "refinement_rows": [
                            _received_trust_refinement_row(
                                "①",
                                "实收本金差异",
                                fa4001,
                                project.received_trust_balance,
                                received_trust_difference,
                                "FA 4001与c1000存在差异",
                            )
                        ],
                        "basis": "c1000 与 FA 4001 不一致，且主差异不能仅由实收本金解释，继续按剩余差额核对负债及权益科目。",
                    },
                )
            )
            self._project_log(
                project,
                f"实收差额不能单独解释主差异，主差异={project.difference}，实收差额={received_trust_difference}，剩余差额={residual_difference}",
                "负债权益科目匹配",
            )

        # c1000 无法解释主差异时，再到估值表非 1 开头科目中排查负债及权益科目差异。
        # 此处不限制最末级科目，因为负债及权益类科目可能直接在上级科目体现差异。
        self._project_log(project, "读取估值表非1开头科目", "负债权益科目匹配")
        valuation_rows = self.repository.list_valuation_rows(
            project.project_code,
            date,
            exclude_prefix="1",
            leaf_only=False,
        )
        self._check_cancelled()
        valuation_rows = _liability_equity_candidate_rows(valuation_rows)
        combination_rows = _liability_equity_combination_rows(valuation_rows)
        self._project_log(project, f"估值表非1开头科目 {len(valuation_rows)} 行，开始匹配差异 {match_difference}", "负债权益科目匹配")
        should_detect_ambiguous_main_difference = (
            detect_main_difference_ambiguity
            and residual_difference is None
            and amounts_equal(match_difference, project.difference)
        )
        valuation_match, match_target = self._find_valuation_match(
            valuation_rows,
            match_difference,
            combination_rows,
            detect_ambiguous_combinations=should_detect_ambiguous_main_difference,
        )
        if valuation_match.match_type == "combination_overflow":
            valuation_match, match_target, _overflow_groups = self._find_natural_group_match_with_target(
                combination_rows,
                match_difference,
                detect_ambiguous_combinations=should_detect_ambiguous_main_difference,
            )
        self._check_cancelled()
        self._project_log(
            project,
            f"负债权益科目匹配结果={valuation_match.match_type}，匹配目标={match_target}，命中金额={valuation_match.total}{'，' + valuation_match.message if valuation_match.message else ''}",
            "负债权益科目匹配",
        )
        resolved = self._is_resolved(valuation_match)
        liability_detail_data = {
            "match_type": valuation_match.match_type,
            "match_total": str(valuation_match.total),
            "match_message": valuation_match.message,
            "match_target": str(match_target),
            "account_scope": "非1开头科目",
            "c1000_balance": str(project.received_trust_balance),
            "fa_4001_balance": str(fa4001),
        }
        liability_reason, liability_rows = _liability_equity_reason_and_rows(
            valuation_match,
            resolved,
            match_difference,
            received_trust_difference if residual_difference is not None else None,
        )
        if valuation_match.match_type == "ambiguous_combination":
            liability_reason = "候选不唯一"
            liability_rows = []
            liability_detail_data["candidate_groups"] = _candidate_groups_payload(valuation_match.candidate_groups)
            liability_detail_data["specific_reason"] = liability_reason
            liability_detail_data["rows"] = liability_rows
            details = detail_prefix + [
                DifferenceDetail(
                    kind="liability_equity",
                    data=liability_detail_data,
                )
            ]
            return self._result(
                project,
                difference_reason=f"{_liability_equity_direction_reason(match_difference)} + 暂无法确定",
                match_status="候选不唯一",
                details=details,
                valuation_match=valuation_match,
                valuation_asset_total=valuation_asset_total,
            )
        positive_repo_refinement = None
        if not resolved:
            positive_repo_refinement = self._positive_repo_liability_equity_refinement(
                project,
                valuation_rows,
                match_difference,
                received_trust_difference if residual_difference is not None else None,
            )
            if positive_repo_refinement is not None:
                liability_reason = positive_repo_refinement["specific_reason"]
                liability_rows = positive_repo_refinement["rows"]
                liability_detail_data.update(
                    {
                        "repo_difference_total": positive_repo_refinement["difference_total"],
                        "positive_repo_fa_total": positive_repo_refinement["fa_total"],
                        "positive_repo_business_amount": positive_repo_refinement["business_amount"],
                    }
                )
        liability_detail_data["specific_reason"] = liability_reason
        liability_detail_data["rows"] = liability_rows
        if residual_difference is not None:
            liability_detail_data.update(
                {
                    "main_difference": str(project.difference),
                    "received_trust_difference": str(received_trust_difference),
                    "residual_difference": str(residual_difference),
                }
            )
        details = detail_prefix + [
            DifferenceDetail(
                kind="liability_equity",
                data=liability_detail_data,
            )
        ]

        if resolved:
            reason = "负债及权益科目缺失" if match_difference > 0 else "负债及权益科目重复"
            return self._result(
                project,
                difference_reason=reason,
                match_status="已解释",
                details=details,
                valuation_match=valuation_match,
                valuation_asset_total=valuation_asset_total,
            )

        if positive_repo_refinement is not None and positive_repo_refinement["is_full_match"]:
            return self._result(
                project,
                difference_reason="负债及权益科目差异",
                match_status="已解释",
                details=details,
                valuation_match=valuation_match,
                valuation_asset_total=valuation_asset_total,
            )

        return self._result(
            project,
            difference_reason="负债及权益科目差异",
            match_status=self._status_for_match(valuation_match),
            details=details,
            valuation_match=valuation_match,
            valuation_asset_total=valuation_asset_total,
        )

    def _positive_repo_liability_equity_refinement(
        self,
        project: ProjectBalance,
        valuation_rows: list[ValuationRow],
        match_difference: Decimal,
        received_trust_difference: Decimal | None,
    ) -> dict[str, Any] | None:
        positive_repo_rows = [row for row in valuation_rows if _is_positive_repo_account(row.account_code)]
        fa_total = _valuation_market_total(positive_repo_rows)
        business_amount = self.repository.get_positive_repo_business_amount(project.project_code)
        difference_total = fa_total - business_amount
        if amounts_equal(difference_total, Decimal("0")):
            return None

        self._project_log(
            project,
            f"正回购：估值={fa_total}，存续回购业务表金额={business_amount}，差异={difference_total}",
            "负债权益回购核对",
        )
        index_number = 2 if received_trust_difference is not None else 1
        reason = f"正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值{difference_total}"
        row = {
            "index": _circled_index(index_number),
            "account_type": "正回购",
            "account_name": "正回购",
            "account_code": _repo_account_code(positive_repo_rows, "2111"),
            "account_tail": "",
            "market_value": str(fa_total),
            "direction": "差异",
            "check_result": "金额差异",
            "reason": reason,
            "business_amount": str(business_amount),
        }
        is_full_match = amounts_equal(difference_total, match_difference)
        if is_full_match:
            positive_repo_reason = f"{row['index']}{reason}"
        else:
            positive_repo_reason = (
                f"{row['index']}暂不明确具体负债及权益科目差异，但正回购，"
                f"FA科目余额与存续回购业务表正回购金额有差异，差异值{difference_total}"
            )
            if received_trust_difference is None:
                positive_repo_reason = positive_repo_reason.removeprefix(row["index"])

        if received_trust_difference is not None:
            specific_reason = f"{_received_trust_difference_reason(received_trust_difference)}\n{positive_repo_reason}"
        else:
            specific_reason = positive_repo_reason

        return {
            "specific_reason": specific_reason,
            "rows": [row],
            "difference_total": str(difference_total),
            "fa_total": str(fa_total),
            "business_amount": str(business_amount),
            "is_full_match": is_full_match,
        }

    def _received_trust_whole_principal_result(
        self,
        project: ProjectBalance,
        date: str,
        fa4001: Decimal,
        reason: str,
        valuation_asset_total: Decimal,
        *,
        repeat_count: int | None = None,
    ) -> ReconcileResult:
        self._project_log(project, f"主差异等于整笔FA 4001，返回{reason}", "实收本金核对")
        detail_reason = f"①{reason}：FA 4001科目余额{fa4001}"
        check_result = "a0001-d0000等于FA 4001科目余额"
        reason_text = ""
        repeat_amount: Decimal | None = None
        if reason == "实收本金缺失":
            has_report_rows = self.repository.has_report_rows(
                ("currency_report_24", "currency_detail_project_2_1_8"),
                date,
            )
            if not has_report_rows:
                reason_text = "资负数据子系统-实收本金明细表无数据"
                detail_reason = f"{detail_reason}；原因：{reason_text}"
        elif reason == "实收本金重复":
            repeat_count = repeat_count or 1
            repeat_amount = fa4001 * Decimal(repeat_count)
            reason_text = f"c1000疑似重复计入{repeat_count}次，重复金额{repeat_amount}"
            detail_reason = f"{detail_reason}；原因：{reason_text}"
            check_result = f"c1000为FA 4001科目余额的{repeat_count + 1}倍，a0001-d0000等于重复金额的相反数"
        received_trust_difference = fa4001 - project.received_trust_balance
        data = {
            "specific_reason": detail_reason,
            "c1000_balance": str(project.received_trust_balance),
            "fa_4001_balance": str(fa4001),
            "received_trust_difference": str(received_trust_difference),
            "valuation_asset_total": str(valuation_asset_total),
            "refinement_rows": [
                _received_trust_refinement_row(
                    "①",
                    reason,
                    fa4001,
                    project.received_trust_balance,
                    received_trust_difference,
                    check_result,
                    reason_text,
                )
            ],
            "basis": "a0001-d0000 的绝对差额等于 FA 4001 科目余额或其实收重复金额。",
        }
        if repeat_count is not None:
            data["repeat_count"] = str(repeat_count)
        if repeat_amount is not None:
            data["repeat_amount"] = str(repeat_amount)
        return self._result(
            project,
            difference_reason=reason,
            match_status="已解释",
            details=[
                DifferenceDetail(
                    kind="received_trust",
                    data=data,
                )
            ],
            valuation_asset_total=valuation_asset_total,
        )

    def _received_trust_result(
        self,
        project: ProjectBalance,
        date: str,
        fa4001: Decimal,
        received_trust_difference: Decimal,
        valuation_asset_total: Decimal,
    ) -> ReconcileResult:
        base_reason = _received_trust_difference_reason(received_trust_difference)
        details = [
            DifferenceDetail(
                kind="received_trust",
                data={
                    "c1000_balance": str(project.received_trust_balance),
                    "fa_4001_balance": str(fa4001),
                    "received_trust_difference": str(received_trust_difference),
                    "valuation_asset_total": str(valuation_asset_total),
                    "specific_reason": base_reason,
                    "refinement_rows": [
                        _received_trust_refinement_row(
                            "①",
                            "实收本金差异",
                            fa4001,
                            project.received_trust_balance,
                            received_trust_difference,
                            "FA 4001与c1000存在差异",
                        )
                    ],
                },
            )
        ]

        self._project_log(project, "核对DM与DWS中TA份额余额+待结转收益", "TA实收信托细分")
        dm_total, dws_total = self.repository.get_ta_balance_totals(project.project_code, date)
        self._check_cancelled()
        if not amounts_equal(dm_total, dws_total):
            total_difference = dm_total - dws_total
            data = {
                "dm_total": str(dm_total),
                "dws_total": str(dws_total),
                "difference": str(total_difference),
            }
            if amounts_equal(abs(total_difference), abs(received_trust_difference)):
                data["specific_reason"] = f"{base_reason}；原因：DM表TA份额余额错误"
            details.append(
                DifferenceDetail(
                    kind="ta_total_mismatch",
                    data=data,
                )
            )
            return self._result(
                project,
                difference_reason="实收本金差异",
                match_status="已解释",
                details=details,
                valuation_asset_total=valuation_asset_total,
            )

        self._project_log(project, "DM与DWS中TA汇总一致，检查DM客户类型为空明细", "TA实收信托细分")
        blank_rows = self.repository.list_blank_ta_client_type_rows(project.project_code, date)
        self._check_cancelled()
        if blank_rows:
            blank_total = sum((Decimal(str(row.get("amount") or "0")) for row in blank_rows), Decimal("0"))
            data = {
                "blank_client_type_total": str(blank_total),
                "rows": [_ta_blank_client_type_detail(row) for row in blank_rows],
            }
            if amounts_equal(blank_total, received_trust_difference):
                data["specific_reason"] = f"{base_reason}；原因：dm.ta_pact_survamt_day_zgxg_dm表中客户类型为空导致实收信托有误"
            details.append(
                DifferenceDetail(
                    kind="ta_blank_client_type",
                    data=data,
                )
            )
            if amounts_equal(blank_total, received_trust_difference):
                return self._result(
                    project,
                    difference_reason="实收本金差异",
                    match_status="已解释",
                    details=details,
                    valuation_asset_total=valuation_asset_total,
                )

        return self._result(
            project,
            difference_reason="实收本金差异",
            match_status="已解释",
            details=details,
            valuation_asset_total=valuation_asset_total,
        )

    def _find_valuation_match(
        self,
        valuation_rows: list[ValuationRow],
        target: Decimal,
        combination_rows: list[ValuationRow] | None = None,
        *,
        detect_ambiguous_combinations: bool = False,
    ) -> tuple[ValuationMatch, Decimal]:
        self._check_cancelled()
        # 先按主差异原符号匹配；如果主差异为负且未命中，再尝试绝对值。
        # 这样可以兼容负债及权益端“多出/缺少”在估值表中用正数体现的情况。
        valuation_match = find_valuation_matches(
            valuation_rows,
            target,
            combination_rows=combination_rows,
            max_combination_rows=self.max_combination_rows,
            detect_ambiguous_combinations=detect_ambiguous_combinations,
            cancel_checker=self._check_cancelled,
        )
        if self._is_resolved(valuation_match) or valuation_match.match_type == "ambiguous_combination" or target >= 0:
            return valuation_match, target

        absolute_target = abs(target)
        absolute_match = find_valuation_matches(
            valuation_rows,
            absolute_target,
            combination_rows=combination_rows,
            max_combination_rows=self.max_combination_rows,
            detect_ambiguous_combinations=detect_ambiguous_combinations,
            cancel_checker=self._check_cancelled,
        )
        self._check_cancelled()
        if self._is_resolved(absolute_match) or absolute_match.match_type == "ambiguous_combination":
            return absolute_match, absolute_target
        return valuation_match, target

    def _find_natural_group_match(
        self,
        valuation_rows: list[ValuationRow],
        target: Decimal,
        *,
        detect_ambiguous_combinations: bool = False,
        max_ambiguous_groups: int = DISPLAY_CANDIDATE_GROUP_LIMIT,
    ) -> tuple[ValuationMatch, set[str]]:
        valuation_match, _target, overflow_groups = self._find_natural_group_match_with_target(
            valuation_rows,
            target,
            detect_ambiguous_combinations=detect_ambiguous_combinations,
            max_ambiguous_groups=max_ambiguous_groups,
        )
        return valuation_match, overflow_groups

    def _find_natural_group_match_with_target(
        self,
        valuation_rows: list[ValuationRow],
        target: Decimal,
        *,
        detect_ambiguous_combinations: bool = False,
        max_ambiguous_groups: int = DISPLAY_CANDIDATE_GROUP_LIMIT,
    ) -> tuple[ValuationMatch, Decimal, set[str]]:
        valuation_match, overflow_groups = self._find_natural_group_match_for_target(
            valuation_rows,
            target,
            detect_ambiguous_combinations=detect_ambiguous_combinations,
            max_ambiguous_groups=max_ambiguous_groups,
        )
        if self._is_resolved(valuation_match) or valuation_match.match_type == "ambiguous_combination" or target >= 0:
            return valuation_match, target, overflow_groups

        absolute_match, absolute_overflow_groups = self._find_natural_group_match_for_target(
            valuation_rows,
            abs(target),
            detect_ambiguous_combinations=detect_ambiguous_combinations,
            max_ambiguous_groups=max_ambiguous_groups,
        )
        overflow_groups.update(absolute_overflow_groups)
        if self._is_resolved(absolute_match) or absolute_match.match_type == "ambiguous_combination":
            return absolute_match, abs(target), overflow_groups
        return valuation_match, target, overflow_groups

    def _find_natural_group_match_for_target(
        self,
        valuation_rows: list[ValuationRow],
        target: Decimal,
        *,
        detect_ambiguous_combinations: bool = False,
        max_ambiguous_groups: int = DISPLAY_CANDIDATE_GROUP_LIMIT,
    ) -> tuple[ValuationMatch, set[str]]:
        overflow_messages: list[str] = []
        overflow_groups: set[str] = set()
        resolved_group_matches: list[tuple[str, ValuationMatch]] = []
        for group_key, group_rows in _natural_grouped_valuation_rows(valuation_rows).items():
            self._check_cancelled()
            group_match = find_valuation_matches(
                group_rows,
                target,
                max_combination_rows=self.max_combination_rows,
                detect_ambiguous_combinations=detect_ambiguous_combinations,
                max_ambiguous_groups=max_ambiguous_groups,
                cancel_checker=self._check_cancelled,
            )
            if group_match.match_type == "ambiguous_combination":
                candidate_groups = _rank_candidate_row_groups(group_match.candidate_groups)
                return (
                    ValuationMatch(
                        match_type="ambiguous_combination",
                        rows=candidate_groups[0],
                        message="候选不唯一",
                        candidate_groups=candidate_groups,
                    ),
                    overflow_groups,
                )
            if self._is_resolved(group_match):
                if detect_ambiguous_combinations:
                    resolved_group_matches.append((group_key, group_match))
                    if len(resolved_group_matches) >= 2:
                        candidate_groups = _rank_candidate_row_groups(
                            [match.rows for _key, match in resolved_group_matches]
                        )
                        return (
                            ValuationMatch(
                                match_type="ambiguous_combination",
                                rows=candidate_groups[0],
                                message="候选不唯一",
                                candidate_groups=candidate_groups,
                            ),
                            overflow_groups,
                        )
                    continue
                return (
                    ValuationMatch(
                        match_type=group_match.match_type,
                        rows=group_match.rows,
                        message=f"分类组合命中：{group_key}",
                    ),
                    overflow_groups,
                )
            if group_match.match_type == "combination_overflow":
                overflow_messages.append(f"{group_key}({len(group_rows)}行)")
                if any(_is_bond_principal_account(row.account_code) for row in group_rows):
                    overflow_groups.add(group_key)

        if detect_ambiguous_combinations and resolved_group_matches:
            group_key, group_match = resolved_group_matches[0]
            return (
                ValuationMatch(
                    match_type=group_match.match_type,
                    rows=group_match.rows,
                    message=f"分类组合命中：{group_key}",
                ),
                overflow_groups,
            )

        if overflow_messages:
            return (
                ValuationMatch(
                    match_type="combination_overflow",
                    message=f"分类组合候选过多：{'、'.join(overflow_messages)}",
                ),
                overflow_groups,
            )
        return ValuationMatch(match_type="none", message="分类组合未命中"), overflow_groups

    def _bond_security_balance_difference_rows(
        self,
        project: ProjectBalance,
        date: str,
        valuation_rows: list[ValuationRow],
        bond_overflow_groups: set[str],
    ) -> list[dict[str, str]]:
        fa_rows = [
            row
            for row in valuation_rows
            if _is_bond_principal_account(row.account_code)
            and (
                not bond_overflow_groups
                or _fourth_level_account_code(row.account_code) in bond_overflow_groups
            )
        ]
        if not fa_rows:
            return []

        fa_amounts: dict[tuple[str, str], Decimal] = {}
        fa_account_codes: dict[tuple[str, str], str] = {}
        for row in fa_rows:
            key = (row.account_tail_code, row.account_name)
            fa_amounts[key] = fa_amounts.get(key, Decimal("0")) + row.market_value
            fa_account_codes.setdefault(key, row.account_code)

        dm_amounts: dict[tuple[str, str], Decimal] = {}
        for row in self.repository.list_security_balance_amounts(project.project_code, date):
            stock_code = str(row.get("stock_code") or "")
            security_name = str(row.get("security_name") or "")
            if not stock_code or not security_name:
                continue
            key = (stock_code, security_name)
            dm_amounts[key] = dm_amounts.get(key, Decimal("0")) + to_decimal(row.get("amount"))

        detail_rows: list[dict[str, str]] = []
        for stock_code, security_name in sorted(set(fa_amounts) | set(dm_amounts), key=lambda item: (item[1], item[0])):
            key = (stock_code, security_name)
            fa_amount = fa_amounts.get(key, Decimal("0"))
            dm_amount = dm_amounts.get(key, Decimal("0"))
            difference = dm_amount - fa_amount
            if amounts_equal(difference, Decimal("0")):
                continue
            reason = _bond_security_difference_reason(security_name, stock_code, fa_amount, dm_amount, difference)
            self._project_log(
                project,
                f"债券{security_name}：FA本金={fa_amount}，DM证券余额={dm_amount}，差异={difference}",
                "资产差异债券DM核对",
            )
            detail_rows.append(
                {
                    "index": "",
                    "asset_type": "债券",
                    "asset_name": security_name,
                    "account_code": fa_account_codes.get(key, ""),
                    "account_name": security_name,
                    "pact_id": "",
                    "security_code": stock_code,
                    "market_value": str(fa_amount),
                    "project_invest_balance": str(dm_amount),
                    "difference": str(difference),
                    "check_table": "dm.fa_security_balance_zgxg_dm",
                    "reason": reason,
                }
            )
        return detail_rows

    def _find_asset_missing_am_reason(
        self,
        project: ProjectBalance,
        date: str,
        valuation_rows: list[ValuationRow],
    ) -> tuple[str, DifferenceDetail] | None:
        self._check_cancelled()
        # 只有资产缺失且命中特定目的载体四级科目时，才进入 AM 标的和合同投融资余额复核。
        self._project_log(project, "读取项目AM资产信息", "AM标的复核")
        project_pact_assets = self.repository.list_project_pact_assets(project.project_code, date)
        self._check_cancelled()
        self._project_log(project, f"项目AM资产信息 {len(project_pact_assets)} 条", "AM标的复核")
        first_normal_result: tuple[str, DifferenceDetail] | None = None
        for valuation_row in valuation_rows:
            check_result = self._asset_missing_am_check_for_row(
                project,
                date,
                valuation_row,
                project_pact_assets,
            )
            if check_result is not None:
                reason, detail, is_abnormal = check_result
                if is_abnormal:
                    return reason, detail
                if first_normal_result is None:
                    first_normal_result = reason, detail
        return first_normal_result

    def _confirm_ambiguous_asset_missing_by_am(
        self,
        project: ProjectBalance,
        date: str,
        valuation_match: ValuationMatch,
        asset_gap: Decimal,
    ) -> tuple[ValuationMatch | None, list[DifferenceDetail]]:
        self._project_log(project, "资产缺失候选不唯一，尝试用AM复核确认候选组合", "AM标的复核")
        project_pact_assets = self.repository.list_project_pact_assets(project.project_code, date)
        confirmed: list[tuple[int, list[ValuationRow], list[DifferenceDetail]]] = []
        for group_index, group in enumerate(_rank_candidate_row_groups(valuation_match.candidate_groups), start=1):
            abnormal_amount = Decimal("0")
            abnormal_details: list[DifferenceDetail] = []
            for valuation_row in group:
                check_result = self._asset_missing_am_check_for_row(
                    project,
                    date,
                    valuation_row,
                    project_pact_assets,
                )
                if check_result is None:
                    continue
                reason, detail, is_abnormal = check_result
                if reason and is_abnormal:
                    abnormal_amount += valuation_row.market_value
                    abnormal_details.append(detail)
            if amounts_equal(abnormal_amount, asset_gap):
                confirmed.append((group_index, group, abnormal_details))

        if len(confirmed) != 1:
            return None, []

        group_index, group, abnormal_details = confirmed[0]
        return (
            ValuationMatch(
                match_type="combination",
                rows=group,
                message=f"候选不唯一，经AM复核确认：候选组合{group_index}",
            ),
            abnormal_details,
        )

    def _asset_missing_am_check_for_row(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
        project_pact_assets: list[PactAssetRow],
    ) -> tuple[str, DifferenceDetail, bool] | None:
        if not _is_special_purpose_vehicle_account(valuation_row.account_code):
            self._project_log(project, f"科目{valuation_row.account_code}不是特定目的载体四级科目，跳过AM复核", "AM标的复核")
            return None

        self._project_log(project, f"按科目名称匹配AM资产：{valuation_row.account_name}", "AM标的复核")
        matched_assets = self._select_pact_assets_for_am_check(project, date, valuation_row, project_pact_assets)
        if not matched_assets:
            self._project_log(project, "未匹配到AM资产名称", "AM标的复核")
            return "AM标的缺失", DifferenceDetail(
                kind="am_missing",
                data={
                    "fa_account_code": valuation_row.account_code,
                    "fa_account_name": valuation_row.account_name,
                    "fa_tail_code": valuation_row.account_tail_code,
                    "fa_market_value": str(valuation_row.market_value),
                    "expected_account_level": _fourth_level_account_code(valuation_row.account_code),
                    "specific_reason": "AM标的缺失",
                },
            ), True

        if len(matched_assets) > 1:
            matched_assets = sorted(
                matched_assets,
                key=lambda p: p.contract_start_date or "",
                reverse=True,
            )
            self._project_log(
                project,
                f"多个AM候选标的，按合同开始日取最新：{matched_assets[0].asset_name}（{matched_assets[0].contract_start_date}）",
                "AM标的复核",
            )

        latest_asset = matched_assets[0]
        if latest_asset.stock_code != valuation_row.account_tail_code:
            self._project_log(
                project,
                f"最新AM标的数量不一致，FA尾码={valuation_row.account_tail_code}，最新AM标的={latest_asset.stock_code}",
                "AM标的复核",
            )
            return "FA与AM标的不一致", DifferenceDetail(
                kind="fa_am",
                data={
                    "fa_account_code": valuation_row.account_code,
                    "fa_account_name": valuation_row.account_name,
                    "fa_tail_code": valuation_row.account_tail_code,
                    "fa_market_value": str(valuation_row.market_value),
                    "am_asset_name": latest_asset.asset_name,
                    "am_stock_code": latest_asset.stock_code,
                    "pact_id": latest_asset.pact_id,
                    "data_source": latest_asset.data_source,
                    "specific_reason": "FA与AM标的不一致",
                },
            ), True

        stock_matched_asset = latest_asset

        self._project_log(project, f"读取AM合同投融资余额，合同{stock_matched_asset.pact_id}", "合同投融资余额核对")
        project_invest_balance = self.repository.get_project_invest_balance(
            project.project_code,
            date,
            stock_matched_asset.pact_id,
        )
        self._check_cancelled()
        self._project_log(project, f"AM合同投融资余额={project_invest_balance}", "合同投融资余额核对")
        is_zero_balance = amounts_equal(project_invest_balance or Decimal("0"), Decimal("0"))
        detail = DifferenceDetail(
            kind="project_invest_balance",
            data={
                "fa_account_code": valuation_row.account_code,
                "fa_account_name": valuation_row.account_name,
                "fa_tail_code": valuation_row.account_tail_code,
                "fa_market_value": str(valuation_row.market_value),
                "am_asset_name": stock_matched_asset.asset_name,
                "am_stock_code": stock_matched_asset.stock_code,
                "pact_id": stock_matched_asset.pact_id,
                "project_invest_balance": "" if project_invest_balance is None else str(project_invest_balance),
                "specific_reason": (
                    "合同投融资余额为0但FA科目余额不为0"
                    if is_zero_balance
                    else ""
                ),
            },
        )
        if is_zero_balance:
            return "合同投融资余额为0但FA科目余额不为0", detail, True
        return "", detail, False

    def _select_pact_assets_for_am_check(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
        project_pact_assets: list[PactAssetRow],
    ) -> list[PactAssetRow]:
        matched_assets = _matching_pact_assets(valuation_row.account_name, project_pact_assets)
        if matched_assets:
            return matched_assets

        stock_code_assets = [
            pact_asset
            for pact_asset in project_pact_assets
            if pact_asset.stock_code == valuation_row.account_tail_code
        ]
        if stock_code_assets:
            self._project_log(
                project,
                f"AM fallback by FA tail code: {valuation_row.account_tail_code}",
                "AM标的复核",
            )
            return stock_code_assets

        return self._jiangsu_trust_parentheses_fallback_assets(project, date, valuation_row, project_pact_assets)

    def _jiangsu_trust_parentheses_fallback_assets(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
        project_pact_assets: list[PactAssetRow],
    ) -> list[PactAssetRow]:
        account_name = valuation_row.account_name or ""
        if JIANGSU_TRUST_TEXT not in account_name:
            return []

        fa_has_parentheses = _has_chinese_parenthetical_part(account_name)
        fa_base_name = _normalize_asset_name(_strip_chinese_parenthetical_parts(account_name))
        if not fa_base_name:
            return []

        candidates: list[PactAssetRow] = []
        for pact_asset in project_pact_assets:
            am_name = pact_asset.asset_name or ""
            am_has_parentheses = _has_chinese_parenthetical_part(am_name)
            if fa_has_parentheses == am_has_parentheses:
                continue
            if fa_has_parentheses:
                left_name = fa_base_name
                right_name = _normalize_asset_name(am_name)
            else:
                left_name = _normalize_asset_name(account_name)
                right_name = _normalize_asset_name(_strip_chinese_parenthetical_parts(am_name))
            if left_name and left_name == right_name:
                candidates.append(pact_asset)

        if not candidates:
            return []

        if not fa_has_parentheses:
            candidate_asset_keys = _distinct_am_asset_keys(candidates)
            if len(candidate_asset_keys) != 1:
                self._project_log(
                    project,
                    f"Jiangsu Trust parentheses fallback found {len(candidate_asset_keys)} AM candidates",
                    "AM标的复核",
                )
                return []

        report_match_count = self.repository.count_report_project_name_matches_without_chinese_parentheses(
            date,
            fa_base_name,
        )
        if report_match_count != 1:
            self._project_log(
                project,
                f"Jiangsu Trust report project match count is {report_match_count}",
                "AM标的复核",
            )
            return []

        self._project_log(
            project,
            "Jiangsu Trust one-sided parentheses fallback matched AM asset",
            "AM标的复核",
        )
        return candidates

    def _asset_missing_refinement_detail(
        self,
        project: ProjectBalance,
        date: str,
        valuation_rows: list[ValuationRow],
    ) -> DifferenceDetail:
        rows = []
        reason_lines = []
        for index, valuation_row in enumerate(valuation_rows, start=1):
            refinement = self._asset_missing_refinement_row(project, date, valuation_row)
            refinement["index"] = _circled_index(index)
            rows.append(refinement)
            line = f"{refinement['index']}{refinement['asset_type']}缺失：{refinement['asset_name']}"
            if refinement.get("reason"):
                line = f"{line}；原因：{refinement['reason']}"
            reason_lines.append(line)
        return DifferenceDetail(
            kind="asset_missing_refinement",
            data={
                "specific_reason": "\n".join(reason_lines),
                "rows": rows,
            },
        )

    def _asset_duplicate_refinement_detail(
        self,
        project: ProjectBalance,
        date: str,
        valuation_rows: list[ValuationRow],
    ) -> DifferenceDetail:
        rows = []
        reason_lines = []
        for index, valuation_row in enumerate(valuation_rows, start=1):
            refinement = self._asset_duplicate_refinement_row(project, date, valuation_row)
            refinement["index"] = _circled_index(index)
            rows.append(refinement)
            line = f"{refinement['index']}{refinement['asset_type']}重复：{refinement['asset_name']}"
            if refinement.get("reason"):
                line = f"{line}；原因：{refinement['reason']}"
            reason_lines.append(line)
        return DifferenceDetail(
            kind="asset_duplicate_refinement",
            data={
                "specific_reason": "\n".join(reason_lines),
                "rows": rows,
            },
        )

    def _asset_duplicate_refinement_row(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
    ) -> dict[str, str]:
        asset_type = _missing_asset_type(valuation_row)
        is_private_fund_security = valuation_row.account_code.startswith("1101.05.06.01")
        asset_name = (
            valuation_row.account_name
            if is_private_fund_security
            else f"{valuation_row.account_code} {valuation_row.account_name}"
        )
        reason = ""
        check_table = ""
        key_field = ""
        am_spv_type = ""
        am_asset_type = ""

        if is_private_fund_security:
            check_table = "am_pactasset_dws"
            key_field = "c_spv_type/c_assettype"
            project_pact_assets = self.repository.list_project_pact_assets(project.project_code, date)
            matched_asset = next(
                (pact_asset for pact_asset in project_pact_assets if pact_asset.stock_code == valuation_row.account_tail_code),
                None,
            )
            if matched_asset is not None:
                am_spv_type = matched_asset.spv_type.strip()
                am_asset_type = matched_asset.asset_type.strip()
                if am_spv_type != "11" and am_asset_type in SPECIAL_PURPOSE_VEHICLE_ASSET_TYPES:
                    reason = "该资产在证券信息表中为私募产品但在AM中不为私募产品"

        return {
            "asset_type": asset_type,
            "asset_name": asset_name,
            "fa_account_code": valuation_row.account_code,
            "account_tail": valuation_row.account_tail_code,
            "fa_market_value": str(valuation_row.market_value),
            "check_table": check_table,
            "check_result": reason or "无异常",
            "key_field": key_field,
            "am_spv_type": am_spv_type,
            "am_asset_type": am_asset_type,
            "reason": reason,
        }

    def _asset_missing_refinement_row(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
    ) -> dict[str, str]:
        asset_type = _missing_asset_type(valuation_row)
        asset_name = (
            f"{valuation_row.account_code} {valuation_row.account_name}"
            if asset_type == "其他资产"
            else valuation_row.account_name
        )
        reason = ""
        check_table = ""
        key_field = ""
        extra_fields: dict[str, str] = {}

        if asset_type == "特定目的载体":
            reason, check_table, key_field, extra_fields = self._special_purpose_vehicle_missing_reason(
                project,
                date,
                valuation_row,
            )
        elif asset_type in {"债券", "股票", "公募基金", "私募基金"}:
            reason, check_table, key_field = self._security_asset_missing_reason(project, date, valuation_row, asset_type)
        elif asset_type == "逆回购":
            check_table = "ass_man_reg.ex_pledge_back"
            if self.repository.has_reverse_repo_blank_rows(project.project_code):
                reason = "存续回购业务表回购金额或佣金存在空数据"
                key_field = "buyback_money/expenses"
        elif asset_type == "贷款":
            reason, check_table, key_field = self._loan_missing_reason(project, date, valuation_row)
        elif asset_type == "股权投资":
            reason, check_table, key_field = self._equity_invest_missing_reason(project, date, valuation_row)
        elif asset_type == "信托计划收益权":
            reason, check_table, key_field = self._trust_plan_income_right_missing_reason(project, date, valuation_row)
        elif asset_type == "资产收益权":
            reason, check_table, key_field = self._asset_income_right_missing_reason(project, date, valuation_row)

        row = {
            "asset_type": asset_type,
            "asset_name": asset_name,
            "fa_account_code": valuation_row.account_code,
            "account_tail": valuation_row.account_tail_code,
            "fa_market_value": str(valuation_row.market_value),
            "check_table": check_table,
            "check_result": reason or "无异常",
            "key_field": key_field,
            "reason": reason,
        }
        row.update(extra_fields)
        return row

    def _security_asset_missing_reason(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
        asset_type: str,
    ) -> tuple[str, str, str]:
        check_table = "dm.fa_security_balance_zgxg_dm"
        security = self.repository.get_security_balance_refinement(
            project.project_code,
            date,
            valuation_row.account_tail_code,
            valuation_row.account_name,
        )
        if security is None:
            return f"该{asset_type}在{SECURITY_BALANCE_TABLE_LABEL}中不存在或金额为0", check_table, ""

        field_by_type = {
            "债券": ("sbm_seclas_h2024", "该债券债券类别_人行字段（sbm_seclas_h2024）为空"),
            "股票": ("sbm_gpgqtype_h", "该股票股票股权类别_人行字段（sbm_gpgqtype_h）为空"),
            "公募基金": ("sbm_fundtype", "该公募基金公募私募_人行字段（sbm_fundtype）为空"),
            "私募基金": ("sbm_fundtype", "该私募基金公募私募_人行字段（sbm_fundtype）为空"),
        }
        field_name, blank_reason = field_by_type[asset_type]
        if _is_blank(security.get(field_name)):
            return blank_reason, check_table, field_name

        report_table = {
            "债券": ("currency_report_24", "currency_detail_project_2_1_4"),
            "股票": ("currency_report_24", "currency_detail_project_2_1_5"),
            "公募基金": ("currency_report_24", "currency_detail_project_2_1_6"),
            "私募基金": ("currency_report_24", "currency_detail_project_2_1_6"),
        }[asset_type]
        report_reason = {
            "债券": "资负数据子系统-债务证券明细表无数据",
            "股票": "资负数据子系统-股票股权明细表无数据",
            "公募基金": "资负数据子系统-特定目的载体明细表无数据",
            "私募基金": "资负数据子系统-特定目的载体明细表无数据",
        }[asset_type]
        if not self.repository.has_report_rows(report_table, date):
            return report_reason, ".".join(report_table), ""
        return "", ".".join(report_table), ""

    def _loan_missing_reason(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
    ) -> tuple[str, str, str]:
        check_table = "dm.am_projinvest_zgxg_dm"
        if self.repository.get_dm_project_invest_refinement(project.project_code, date, valuation_row.account_tail_code) is None:
            return f"该贷款在{DM_PROJECT_INVEST_TABLE_LABEL}不存在或投融资余额为0", check_table, ""
        report_table = ("currency_report_24", "currency_detail_project_2_1_2")
        if not self.repository.has_report_rows(report_table, date):
            return "资负数据子系统-除回购和拆借外贷款明细表无数据", ".".join(report_table), ""
        return "", ".".join(report_table), ""

    def _equity_invest_missing_reason(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
    ) -> tuple[str, str, str]:
        check_table = "dm.am_projinvest_zgxg_dm"
        row = self.repository.get_dm_project_invest_refinement(project.project_code, date, valuation_row.account_tail_code)
        if row is None:
            return f"该股权投资在{DM_PROJECT_INVEST_TABLE_LABEL}不存在或投融资余额为0", check_table, ""
        if _is_blank(row.get("pin_gqtype_h")):
            return "该股权投资股权投资类别字段（pin_gqtype_h）为空", check_table, "pin_gqtype_h"
        report_table = ("currency_report_24", "currency_detail_project_2_1_5_2")
        if not self.repository.has_report_rows(report_table, date):
            return "资负数据子系统-股权明细表无数据", ".".join(report_table), ""
        return "", ".".join(report_table), ""

    def _trust_plan_income_right_missing_reason(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
    ) -> tuple[str, str, str]:
        check_table = "dm.am_projinvest_spv_zgxg_dm"
        if self.repository.get_spv_project_invest_refinement(project.project_code, date, valuation_row.account_tail_code) is None:
            return f"该信托计划收益权在{DM_SPV_PROJECT_INVEST_TABLE_LABEL}不存在或余额为0", check_table, ""
        report_table = ("currency_report_24", "currency_detail_project_2_1_6")
        if not self.repository.has_report_rows(report_table, date):
            return "资负数据子系统-特定目的载体明细表无数据", ".".join(report_table), ""
        return "", ".".join(report_table), ""

    def _asset_income_right_missing_reason(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
    ) -> tuple[str, str, str]:
        check_table = "zgxg_zhbs.ccqxx"
        if self.repository.get_property_right_refinement(project.project_code, valuation_row.account_tail_code) is None:
            return f"该财产权在{PROPERTY_RIGHT_CONTRACT_TABLE_LABEL}不存在或投融资余额为0", check_table, ""
        report_table = ("currency_report_24", "currency_detail_project_2_1_9")
        if not self.repository.has_report_rows(report_table, date):
            return "资负数据子系统-其他债权明细表无数据", ".".join(report_table), ""
        return "", ".".join(report_table), ""

    def _special_purpose_vehicle_missing_reason(
        self,
        project: ProjectBalance,
        date: str,
        valuation_row: ValuationRow,
    ) -> tuple[str, str, str, dict[str, str]]:
        project_pact_assets = self.repository.list_project_pact_assets(project.project_code, date)
        matched_assets = self._select_pact_assets_for_am_check(project, date, valuation_row, project_pact_assets)
        if not matched_assets:
            return "AM标的缺失", "am_pactasset_dws", "", {}

        # 多候选时按合同开始日倒序排序，取最新合同
        if len(matched_assets) > 1:
            matched_assets = sorted(
                matched_assets,
                key=lambda p: p.contract_start_date or "",
                reverse=True,
            )
            self._project_log(
                project,
                f"细化详情多候选，按合同开始日取最新：{matched_assets[0].asset_name}（{matched_assets[0].contract_start_date}）",
                "AM标的消歧",
            )

        # 先取最新合同，再判断stock_code是否匹配
        latest_asset = matched_assets[0]
        if latest_asset.stock_code != valuation_row.account_tail_code:
            return "FA和AM标的不一致", "am_pactasset_dws", "c_stockcode", _pact_asset_detail_fields(latest_asset)

        stock_matched_asset = latest_asset

        project_invest_balance = self.repository.get_project_invest_balance(
            project.project_code,
            date,
            stock_matched_asset.pact_id,
        )
        if amounts_equal(project_invest_balance or Decimal("0"), Decimal("0")):
            return "合同投融资余额为0但FA科目余额不为0", "am_projinvest_dws", "f_acbalance", _pact_asset_detail_fields(stock_matched_asset)

        spv_row = self.repository.get_spv_project_invest_refinement(project.project_code, date, stock_matched_asset.pact_id)
        if spv_row is None:
            return f"该特定目的载体在{DM_SPV_PROJECT_INVEST_TABLE_LABEL}不存在或余额为0", "dm.am_projinvest_spv_zgxg_dm", "", _pact_asset_detail_fields(stock_matched_asset)

        if "收益凭证" in stock_matched_asset.asset_name:
            report_table = ("currency_report_24", "currency_detail_project_2_1_9")
            if not self.repository.has_report_rows(report_table, date):
                return "该收益凭证在资负数据子系统-其他债权明细表无数据", ".".join(report_table), "", _pact_asset_detail_fields(stock_matched_asset)
            return "", ".".join(report_table), "", _pact_asset_detail_fields(stock_matched_asset)

        asset_type = str(spv_row.get("svd_assettype") or "").strip()
        if asset_type not in SPECIAL_PURPOSE_VEHICLE_ASSET_TYPES:
            return "该特定目的载体资产类型为空或资产类型有误", "dm.am_projinvest_spv_zgxg_dm", "svd_assettype", _pact_asset_detail_fields(stock_matched_asset)

        report_table = ("currency_report_24", "currency_detail_project_2_1_6")
        if not self.repository.has_report_rows(report_table, date):
            return "资负数据子系统-特定目的载体明细表无数据", ".".join(report_table), "", _pact_asset_detail_fields(stock_matched_asset)
        return "", ".".join(report_table), "", _pact_asset_detail_fields(stock_matched_asset)

    def _status_for_match(self, valuation_match: ValuationMatch) -> str:
        if valuation_match.match_type in {"single", "grouped", "combination"}:
            return "已解释"
        if valuation_match.match_type == "ambiguous_combination":
            return "候选不唯一"
        if valuation_match.match_type == "combination_overflow":
            return "组合候选过多"
        return "未解释"

    def _is_resolved(self, valuation_match: ValuationMatch) -> bool:
        return valuation_match.match_type in {"single", "grouped", "combination"}

    def _unknown_result(
        self,
        project: ProjectBalance,
        details: list[DifferenceDetail],
        valuation_match: ValuationMatch | None = None,
        valuation_asset_total: Decimal | None = None,
    ) -> ReconcileResult:
        return self._result(
            project,
            difference_reason="暂无法确定",
            match_status=self._status_for_match(valuation_match) if valuation_match else "未解释",
            details=details,
            valuation_match=valuation_match,
            valuation_asset_total=valuation_asset_total,
        )

    def _result(
        self,
        project: ProjectBalance,
        *,
        difference_reason: str,
        match_status: str,
        details: list[DifferenceDetail],
        valuation_match: ValuationMatch | None = None,
        valuation_asset_total: Decimal | None = None,
    ) -> ReconcileResult:
        if valuation_asset_total is None:
            valuation_asset_total = _detail_valuation_asset_total(details)
        return ReconcileResult(
            project_code=project.project_code,
            project_name=project.project_name,
            asset_total=project.asset_total,
            liability_equity_total=project.liability_equity_total,
            received_trust_balance=project.received_trust_balance,
            difference=project.difference,
            direction=project.direction,
            difference_reason=difference_reason,
            match_status=match_status,
            valuation_asset_total=valuation_asset_total,
            details=details,
            valuation_match=valuation_match,
        )


def _matching_pact_assets(account_name: str, pact_assets: list[PactAssetRow]) -> list[PactAssetRow]:
    scored_assets = [
        (_asset_name_similarity(account_name, pact_asset.asset_name), pact_asset)
        for pact_asset in pact_assets
    ]
    exact_assets = [pact_asset for score, pact_asset in scored_assets if score == Decimal("1")]
    if exact_assets:
        return exact_assets

    high_similarity_assets = [
        (score, pact_asset)
        for score, pact_asset in scored_assets
        if score >= Decimal("0.90")
    ]
    if not high_similarity_assets:
        return []

    best_score = max(score for score, _ in high_similarity_assets)
    return [
        pact_asset
        for score, pact_asset in high_similarity_assets
        if score == best_score
    ]


def _with_asset_type_specific_reason(
    data: dict[str, Any],
    reason: str,
    rows: list[ValuationRow],
) -> dict[str, Any]:
    asset_types = _matched_asset_types(rows)
    if asset_types:
        suffix = "资产缺失" if reason == "资产缺失" else "资产重复"
        data["specific_reason"] = f"{'、'.join(asset_types)}{suffix}"
    return data


def _received_trust_difference_reason(difference: Decimal) -> str:
    return f"①实收本金差异：FA 4001与c1000存在差异，差异值{difference}"


def _received_trust_duplicate_count(fa4001: Decimal, c1000: Decimal, difference: Decimal) -> int | None:
    if fa4001 <= 0 or c1000 <= fa4001:
        return None
    received_trust_difference = fa4001 - c1000
    if not amounts_equal(received_trust_difference, difference):
        return None
    multiple = c1000 / fa4001
    if multiple != multiple.to_integral_value():
        return None
    repeat_count = int(multiple) - 1
    if repeat_count < 1:
        return None
    return repeat_count


def _received_trust_refinement_row(
    index: str,
    type_name: str,
    fa4001: Decimal,
    c1000: Decimal,
    difference: Decimal,
    check_result: str,
    reason: str = "",
) -> dict[str, str]:
    return {
        "index": index,
        "type": type_name,
        "fa_4001_balance": str(fa4001),
        "c1000_balance": str(c1000),
        "difference": str(difference),
        "check_table": "fa_accountbalance_dws/余额表c1000",
        "check_result": check_result,
        "reason": reason,
    }


def _liability_equity_reason_and_rows(
    valuation_match: ValuationMatch,
    resolved: bool,
    match_difference: Decimal,
    received_trust_difference: Decimal | None,
) -> tuple[str, list[dict[str, str]]]:
    if not resolved:
        reason = "暂不明确具体负债及权益科目差异"
        if received_trust_difference is not None:
            reason = f"{_received_trust_difference_reason(received_trust_difference)}\n②{reason}"
        return reason, []

    direction = "缺失" if match_difference > 0 else "重复"
    start_index = 2 if received_trust_difference is not None else 1
    rows = [
        _liability_equity_refinement_row(row, direction, start_index + offset)
        for offset, row in enumerate(valuation_match.rows)
    ]
    reason_lines = [f"{row['index']}{row['reason_text']}" for row in rows]
    if received_trust_difference is not None:
        reason_lines.insert(0, _received_trust_difference_reason(received_trust_difference))
    return "\n".join(reason_lines), rows


def _liability_equity_direction_reason(match_difference: Decimal) -> str:
    return "负债及权益科目缺失" if match_difference > 0 else "负债及权益科目重复"


def _candidate_groups_payload(candidate_groups: list[list[ValuationRow]]) -> list[dict[str, Any]]:
    payload = []
    for group_index, group in enumerate(
        _rank_candidate_row_groups(candidate_groups, limit=DISPLAY_CANDIDATE_GROUP_LIMIT),
        start=1,
    ):
        payload.append(
            {
                "index": f"候选组合{group_index}",
                "total": str(_valuation_market_total(group)),
                "rows": [
                    {
                        "account_code": row.account_code,
                        "account_name": row.account_name,
                        "account_tail": row.account_tail_code,
                        "market_value": str(row.market_value),
                    }
                    for row in group
                ],
            }
        )
    return payload


def _rank_candidate_row_groups(candidate_groups: list[list[ValuationRow]], limit: int | None = None) -> list[list[ValuationRow]]:
    ranked = sorted(
        candidate_groups,
        key=lambda group: (len(group), [row.account_code for row in group]),
    )
    if limit is None:
        return ranked
    return ranked[:limit]


def _liability_equity_refinement_row(row: ValuationRow, direction: str, index: int) -> dict[str, str]:
    if _is_common_account_level(row.account_code):
        account_type = COMMON_PAYABLE_ACCOUNT_TYPE
    elif _is_positive_repo_account(row.account_code):
        account_type = "正回购"
    else:
        account_type = "负债及权益科目"
    asset_name = row.account_name or row.account_code
    if account_type == "正回购":
        reason = "正回购差异"
    elif account_type == COMMON_PAYABLE_ACCOUNT_TYPE:
        reason = "3001共同类科目为负数，按绝对值参与负债权益核对"
    else:
        reason = ""
    reason_text = f"{account_type}{direction}：{asset_name}"
    if reason:
        reason_text = f"{reason_text}；原因：{reason}"
    return {
        "index": _circled_index(index),
        "account_type": account_type,
        "account_name": asset_name,
        "account_code": row.account_code,
        "account_tail": row.account_tail_code,
        "market_value": str(row.market_value),
        "direction": direction,
        "check_result": "命中",
        "reason": reason,
        "reason_text": reason_text,
    }


def _matched_asset_types(rows: list[ValuationRow]) -> list[str]:
    asset_types: list[str] = []
    for row in rows:
        asset_type = _asset_type_from_account_code(row.account_code)
        if asset_type and asset_type not in asset_types:
            asset_types.append(asset_type)
    return asset_types


def _natural_grouped_valuation_rows(rows: list[ValuationRow]) -> dict[str, list[ValuationRow]]:
    grouped_rows: dict[str, list[ValuationRow]] = {}
    for row in rows:
        grouped_rows.setdefault(_fourth_level_account_code(row.account_code), []).append(row)
    return grouped_rows


def _asset_type_from_account_code(account_code: str) -> str:
    if _is_common_account_level(account_code):
        return COMMON_RECEIVABLE_ASSET_TYPE
    asset_type = _missing_asset_type(ValuationRow(account_code=account_code, account_name="", market_value=Decimal("0")))
    if asset_type in {"公募基金", "私募基金"}:
        return "基金"
    if asset_type != "其他资产":
        return asset_type
    return ""


SPECIAL_PURPOSE_VEHICLE_ACCOUNT_LEVELS = {
    "1101.05.01.01",
    "1101.05.02.01",
    "1101.05.03.01",
    "1101.05.04.01",
    "1101.05.05.01",
    "1101.05.07.01",
}

SPECIAL_PURPOSE_VEHICLE_ASSET_TYPES = {"31", "32", "34", "35", "37", "33", "38"}


def _is_special_purpose_vehicle_account(account_code: str) -> bool:
    account_level = _fourth_level_account_code(account_code)
    return account_level in SPECIAL_PURPOSE_VEHICLE_ACCOUNT_LEVELS or _is_150103_special_purpose_vehicle_account_level(account_level)


def _is_150103_special_purpose_vehicle_account_level(account_level: str) -> bool:
    parts = account_level.split(".")
    return len(parts) == 4 and parts[0] == "1501" and parts[1] == "03" and bool(parts[2]) and parts[3] == "01"


def _missing_asset_type(row: ValuationRow) -> str:
    account_code = row.account_code
    if _is_common_account_level(account_code):
        return COMMON_RECEIVABLE_ASSET_TYPE
    if _is_special_purpose_vehicle_account(account_code):
        return "特定目的载体"
    if account_code.startswith("1501.01") or account_code.startswith("1101.02"):
        return "债券"
    if account_code.startswith("1101.01"):
        return "股票"
    if account_code.startswith("1101.04"):
        return "公募基金"
    if account_code.startswith("1101.05.06"):
        return "私募基金"
    if _is_reverse_repo_account(account_code):
        return "逆回购"
    if account_code.startswith("1303.01.01") or account_code.startswith("1501.04.05.01"):
        return "贷款"
    if account_code.startswith("1511.01.01"):
        return "股权投资"
    if account_code.startswith("1541.01"):
        if _is_trust_plan_income_right_name(row.account_name):
            return "信托计划收益权"
        return "资产收益权"
    return "其他资产"


def _is_trust_plan_income_right_name(account_name: str) -> bool:
    return (
        account_name.startswith("江苏信托")
        and ("信托产品" in account_name or "资金信托计划" in account_name)
    )


def _asset_difference_contract_type(row: ValuationRow) -> str | None:
    if (
        (row.account_code.startswith("1303.01.01") or row.account_code.startswith("1501.04.05.01"))
        and (row.account_tail_code.startswith("DK") or row.account_tail_code.startswith("ZQ"))
    ):
        return "贷款合同"
    if row.account_code.startswith("1541"):
        return "财产权合同"
    return None


def _is_bond_principal_account(account_code: str) -> bool:
    parts = account_code.split(".")
    if len(parts) < 4:
        return False
    return (
        parts[0] == "1501"
        and parts[1] == "01"
        and parts[3] == "01"
    ) or (
        parts[0] == "1101"
        and parts[1] == "02"
        and parts[3] == "01"
    )


def _bond_security_difference_reason(
    security_name: str,
    stock_code: str,
    fa_amount: Decimal,
    dm_amount: Decimal,
    difference: Decimal,
) -> str:
    label = f"{security_name}债券"
    if amounts_equal(dm_amount, Decimal("0")) and not amounts_equal(fa_amount, Decimal("0")):
        return f"{label}：DM中缺少该债券，债券代码{stock_code}，FA债券本金科目余额{fa_amount}"
    if amounts_equal(fa_amount, Decimal("0")) and not amounts_equal(dm_amount, Decimal("0")):
        return f"{label}：FA估值表缺少该债券，债券代码{stock_code}，DM证券余额{dm_amount}"
    return f"{label}：FA债券本金科目余额与DM证券余额有差异，债券代码{stock_code}，差异值{difference}"


def _asset_difference_contract_label(asset_name: str, contract_type: str) -> str:
    if contract_type == "贷款合同" and asset_name.endswith("贷款"):
        return f"{asset_name}合同"
    if contract_type == "财产权合同" and asset_name.endswith("财产权"):
        return f"{asset_name}合同"
    return f"{asset_name}{contract_type}"


def _joined_contract_types(asset_types: Any) -> str:
    ordered_types: list[str] = []
    for asset_type in asset_types:
        if asset_type and asset_type not in ordered_types:
            ordered_types.append(str(asset_type))
    if ordered_types == ["贷款合同", "财产权合同"] or ordered_types == ["财产权合同", "贷款合同"]:
        return "贷款/财产权合同"
    return "、".join(ordered_types) or "贷款/财产权合同"


def _asset_difference_partial_reason(detail_rows: list[dict[str, str]], difference_total: Decimal) -> str:
    asset_types = [row["asset_type"] for row in detail_rows]
    if asset_types and all(asset_type == "债券" for asset_type in asset_types):
        subject = f"{detail_rows[0]['asset_name']}债券" if len(detail_rows) == 1 else "多个债券"
        return f"暂不明确具体资产差异，但{subject}，FA债券本金科目余额与DM证券余额有差异，差异值{difference_total}"
    if "债券" in asset_types:
        subjects = ["多个债券" if sum(1 for asset_type in asset_types if asset_type == "债券") > 1 else f"{next(row['asset_name'] for row in detail_rows if row['asset_type'] == '债券')}债券"]
        non_bond_rows = [row for row in detail_rows if row["asset_type"] != "债券"]
        if non_bond_rows:
            subjects.append(_joined_contract_types(row["asset_type"] for row in non_bond_rows))
        return f"暂不明确具体资产差异，但{'、'.join(subject for subject in subjects if subject)}，FA科目余额与DM证券余额/AM投融资余额/存续回购业务表金额有差异，差异值{difference_total}"
    joined_types = _joined_contract_types(asset_types)
    if asset_types and all(asset_type == "逆回购" for asset_type in asset_types):
        return f"暂不明确具体资产差异，但逆回购，FA科目余额与存续回购业务表逆回购金额有差异，差异值{difference_total}"
    if "逆回购" in asset_types:
        return f"暂不明确具体资产差异，但{joined_types}，FA科目余额与AM投融资余额/存续回购业务表金额有差异，差异值{difference_total}"
    return f"暂不明确具体资产差异，但{joined_types}，FA科目余额与AM投融资余额有差异，差异值{difference_total}"


def _asset_difference_full_reason(detail_rows: list[dict[str, str]]) -> str:
    bond_rows = [row for row in detail_rows if row.get("asset_type") == "债券"]
    if len(bond_rows) <= 1:
        return "\n".join(
            f"{_circled_index(index)}{row['reason']}"
            for index, row in enumerate(detail_rows, start=1)
        )

    reason_lines = []
    next_index = 1
    bond_difference_total = sum(Decimal(str(row.get("difference", "0") or "0")) for row in bond_rows)
    reason_lines.append(
        f"{_circled_index(next_index)}多个债券：FA债券本金科目余额与DM证券余额有差异，差异值{bond_difference_total}"
    )
    next_index += 1
    for row in detail_rows:
        if row.get("asset_type") == "债券":
            continue
        reason_lines.append(f"{_circled_index(next_index)}{row['reason']}")
        next_index += 1
    return "\n".join(reason_lines)


def _valuation_market_total(rows: list[ValuationRow]) -> Decimal:
    return sum((row.market_value for row in rows), Decimal("0"))


def _repo_account_code(rows: list[ValuationRow], account_prefix: str) -> str:
    codes = []
    for row in rows:
        code = _fourth_level_account_code(row.account_code)
        if code and code not in codes:
            codes.append(code)
    if len(codes) == 1:
        return codes[0]
    if codes:
        return f"多个{account_prefix}回购科目"
    return ""


def _repo_account_name(rows: list[ValuationRow], default: str) -> str:
    names = []
    for row in rows:
        name = row.account_name.strip()
        if name and name not in names:
            names.append(name)
    if len(names) == 1:
        return names[0]
    if names:
        return f"多个{default}科目"
    return default


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


_CIRCLED_NUMBERS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _last_specific_reason(details: list[DifferenceDetail]) -> str:
    for detail in reversed(details):
        reason = detail.data.get("specific_reason")
        if reason:
            return str(reason)
    return ""


def _followup_difference_reason(result: ReconcileResult) -> str:
    reasons: list[str] = []
    has_received_trust = any(detail.kind == "received_trust" for detail in result.details)
    if has_received_trust and not str(result.difference_reason).startswith("实收本金"):
        reasons.append("实收本金差异")
    reasons.append(result.difference_reason)
    return " + ".join(dict.fromkeys(reason for reason in reasons if reason))


def _ensure_reason_index(reason: str, index: int) -> str:
    text = str(reason or "")
    if not text:
        return text
    if text[0] in _CIRCLED_NUMBERS:
        return text
    return f"{_circled_index(index)}{text}"


def _renumber_specific_reason(reason: str) -> str:
    next_index = 1
    lines = []
    for line in str(reason or "").splitlines():
        if re.match(f"^([{_CIRCLED_NUMBERS}]|\\d+\\.)", line):
            line = re.sub(f"^([{_CIRCLED_NUMBERS}]|\\d+\\.)", _circled_index(next_index), line, count=1)
            next_index += 1
        lines.append(line)
    return "\n".join(lines)


def _set_last_specific_reason(details: list[DifferenceDetail], reason: str) -> None:
    for detail in reversed(details):
        if detail.data.get("specific_reason"):
            detail.data["specific_reason"] = reason
            return


def _shift_detail_indices(details: list[DifferenceDetail], start_index: int) -> list[DifferenceDetail]:
    return [
        DifferenceDetail(kind=detail.kind, data=_shift_circled_indices(detail.data, start_index))
        for detail in details
    ]


def _shift_circled_indices(value: Any, start_index: int) -> Any:
    if isinstance(value, str):
        return re.sub(
            f"[{_CIRCLED_NUMBERS}]",
            lambda match: _circled_index(start_index + _CIRCLED_NUMBERS.index(match.group(0))),
            value,
        )
    if isinstance(value, list):
        return [_shift_circled_indices(item, start_index) for item in value]
    if isinstance(value, tuple):
        return tuple(_shift_circled_indices(item, start_index) for item in value)
    if isinstance(value, dict):
        return {key: _shift_circled_indices(item, start_index) for key, item in value.items()}
    return value


def _circled_index(index: int) -> str:
    if 1 <= index <= len(_CIRCLED_NUMBERS):
        return _CIRCLED_NUMBERS[index - 1]
    return f"{index}."


def _is_reverse_repo_account(account_code: str) -> bool:
    parts = account_code.split(".")
    return len(parts) >= 4 and parts[0] == "1111" and len(parts[1]) == 2 and len(parts[2]) == 2 and parts[3] == "01"


def _is_positive_repo_account(account_code: str) -> bool:
    parts = account_code.split(".")
    return len(parts) >= 4 and parts[0] == "2111" and len(parts[1]) == 2 and len(parts[2]) == 2 and parts[3] == "01"


def _is_positive_repo_interest_account(account_code: str) -> bool:
    parts = account_code.split(".")
    return len(parts) >= 4 and parts[0] == "2111" and len(parts[1]) == 2 and len(parts[2]) == 2 and parts[3] == "02"


def _is_zero_prefixed_four_digit_account(account_code: str) -> bool:
    return len(account_code) == 4 and account_code.startswith("0") and account_code.isdigit()


def _is_common_account_level(account_code: str) -> bool:
    parts = account_code.split(".")
    return len(parts) == 2 and parts[0] == "3001" and bool(parts[1])


def _is_common_account_descendant(account_code: str) -> bool:
    return account_code.startswith("3001.") and not _is_common_account_level(account_code)


def _normalize_common_payable_row(row: ValuationRow) -> ValuationRow:
    return ValuationRow(row.account_code, row.account_name, abs(row.market_value))


def _asset_gap_candidate_rows(rows: list[ValuationRow]) -> list[ValuationRow]:
    asset_rows = _actual_leaf_rows([row for row in rows if row.account_code.startswith("1")])
    common_receivable_rows = [
        row
        for row in rows
        if _is_common_account_level(row.account_code) and row.market_value > 0
    ]
    return asset_rows + common_receivable_rows


def _liability_equity_candidate_rows(rows: list[ValuationRow]) -> list[ValuationRow]:
    candidate_rows: list[ValuationRow] = []
    for row in rows:
        if _is_zero_prefixed_four_digit_account(row.account_code):
            continue
        if _is_common_account_descendant(row.account_code):
            continue
        if _is_common_account_level(row.account_code):
            if row.market_value < 0:
                candidate_rows.append(_normalize_common_payable_row(row))
            continue
        candidate_rows.append(row)
    return candidate_rows


def _liability_equity_combination_rows(rows: list[ValuationRow]) -> list[ValuationRow]:
    return [
        row
        for row in _actual_leaf_rows(rows)
        if not _is_positive_repo_interest_account(row.account_code)
    ]


def _actual_leaf_rows(rows: list[ValuationRow]) -> list[ValuationRow]:
    account_codes = [row.account_code for row in rows]
    return [
        row
        for row in rows
        if not any(code != row.account_code and code.startswith(f"{row.account_code}.") for code in account_codes)
    ]


def _detail_valuation_asset_total(details: list[DifferenceDetail]) -> Decimal | None:
    for detail in details:
        value = detail.data.get("valuation_asset_total")
        if value not in (None, ""):
            return Decimal(str(value))
    return None


def _pact_asset_detail_fields(pact_asset: PactAssetRow) -> dict[str, str]:
    return {
        "am_asset_name": pact_asset.asset_name,
        "am_stock_code": pact_asset.stock_code,
        "pact_id": pact_asset.pact_id,
        "data_source": pact_asset.data_source,
    }


def _ta_blank_client_type_detail(row: dict[str, Any]) -> dict[str, str]:
    return {
        "pact_id": str(row.get("pact_id") or ""),
        "client_name": str(row.get("client_name") or ""),
        "client_kind": str(row.get("client_kind") or ""),
        "client_kind_index": str(row.get("client_kind_index") or ""),
        "spv_type": str(row.get("spv_type") or ""),
        "ht_income": str(row.get("ht_income") or "0"),
        "share_amount": str(row.get("share_amount") or "0"),
        "amount": str(row.get("amount") or "0"),
    }


def _fourth_level_account_code(account_code: str) -> str:
    parts = account_code.split(".")
    if len(parts) < 4:
        return account_code
    return ".".join(parts[:4])


def _asset_name_similarity(left: str, right: str) -> Decimal:
    left_name = _normalize_asset_name(left)
    right_name = _normalize_asset_name(right)
    if not left_name or not right_name:
        return Decimal("0")
    if left_name == right_name:
        return Decimal("1")
    if _parenthetical_parts(left_name) != _parenthetical_parts(right_name):
        return Decimal("0")
    if min(len(left_name), len(right_name)) < 4:
        return Decimal("0")
    ratio = SequenceMatcher(None, left_name, right_name).ratio()
    return Decimal(str(round(ratio, 4)))


def _normalize_asset_name(value: str) -> str:
    name = unicodedata.normalize("NFKC", value or "").strip().lower()
    name = re.sub(r"\s+", "", name)
    name = re.sub(r"[_＿][^_＿]+$", "", name)
    return name


def _has_chinese_parenthetical_part(value: str) -> bool:
    return bool(CHINESE_PAREN_RE.search(value or ""))


def _strip_chinese_parenthetical_parts(value: str) -> str:
    return CHINESE_PAREN_RE.sub("", value or "")


def _distinct_am_asset_keys(pact_assets: list[PactAssetRow]) -> set[tuple[str, str]]:
    return {(pact_asset.asset_name, pact_asset.stock_code) for pact_asset in pact_assets}


def _parenthetical_parts(value: str) -> list[str]:
    return re.findall(r"\(([^()]*)\)", value)
