from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ProjectBalance:
    project_code: str
    project_name: str
    asset_total: Decimal
    liability_equity_total: Decimal
    received_trust_balance: Decimal = Decimal("0")

    @property
    def difference(self) -> Decimal:
        return self.asset_total - self.liability_equity_total

    @property
    def direction(self) -> str:
        if self.difference > 0:
            return "资产大于负债及权益"
        if self.difference < 0:
            return "资产小于负债及权益"
        return "无差异"


@dataclass(frozen=True)
class ValuationRow:
    account_code: str
    account_name: str
    market_value: Decimal

    @property
    def account_tail_code(self) -> str:
        return self.account_code.rsplit(".", 1)[-1]


@dataclass(frozen=True)
class ValuationMatch:
    match_type: str
    rows: list[ValuationRow] = field(default_factory=list)
    message: str = ""
    candidate_groups: list[list[ValuationRow]] = field(default_factory=list)

    @property
    def total(self) -> Decimal:
        return sum((row.market_value for row in self.rows), Decimal("0"))


@dataclass(frozen=True)
class PactAssetRow:
    project_code: str
    asset_name: str
    stock_code: str
    pact_id: str = ""
    spv_type: str = ""
    asset_type: str = ""


@dataclass(frozen=True)
class DifferenceDetail:
    kind: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ReconcileResult:
    project_code: str
    project_name: str
    asset_total: Decimal
    liability_equity_total: Decimal
    received_trust_balance: Decimal
    difference: Decimal
    direction: str
    difference_reason: str
    match_status: str
    valuation_asset_total: Decimal | None = None
    details: list[DifferenceDetail] = field(default_factory=list)
    valuation_match: ValuationMatch | None = None
