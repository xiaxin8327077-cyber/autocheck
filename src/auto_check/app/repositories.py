from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from auto_check.app.config import AppConfig
from auto_check.app.db import DatabaseClient, qualified_name
from auto_check.app.pbc_import import TableRef
from auto_check.engine.models import PactAssetRow, ProjectBalance, ValuationRow
from auto_check.engine.money import to_decimal


class AutoCheckRepository:
    def __init__(
        self,
        config: AppConfig,
        *,
        dws_client: DatabaseClient | None = None,
        business_client: DatabaseClient | None = None,
    ):
        self.config = config
        self.dws_client = dws_client or DatabaseClient(config.dws)
        self.business_client = business_client or DatabaseClient(config.business)
        self._fa4001_cache: dict[str, dict[str, Decimal]] = {}
        self._valuation_asset_total_cache: dict[str, dict[str, Decimal]] = {}
        self._valuation_rows_cache: dict[str, dict[str, list[ValuationRow]]] = {}
        self._pact_asset_cache: dict[str, dict[tuple[str, str], list[PactAssetRow]]] = {}
        self._project_pact_asset_cache: dict[str, dict[str, list[PactAssetRow]]] = {}
        self._project_invest_balance_cache: dict[str, dict[tuple[str, str], Decimal]] = {}
        self._ta_balance_totals_cache: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
        self._blank_ta_client_type_cache: dict[str, dict[str, list[dict[str, Decimal | str]]]] = {}

    def list_project_balances(self, date: str) -> list[ProjectBalance]:
        table = qualified_name(self.config.business, "zf_detail_2024")
        rows = self.business_client.fetch_all(
            f"""
            SELECT projinnercode, projname, a0001, d0000, c1000
            FROM {table}
            WHERE caldate = %s
            """,
            (date,),
        )
        return [
            ProjectBalance(
                project_code=str(row["projinnercode"]),
                project_name=str(row.get("projname") or ""),
                asset_total=to_decimal(row.get("a0001")),
                liability_equity_total=to_decimal(row.get("d0000")),
                received_trust_balance=to_decimal(row.get("c1000")),
            )
            for row in rows
        ]

    def get_fa_4001_balance(self, project_code: str, date: str) -> Decimal:
        return self._fa4001_by_date(date).get(project_code, Decimal("0"))

    def _fa4001_by_date(self, date: str) -> dict[str, Decimal]:
        if date in self._fa4001_cache:
            return self._fa4001_cache[date]

        table = qualified_name(self.config.dws, "fa_accountbalance_dws")
        rows = self.dws_client.fetch_all(
            f"""
            SELECT c_projcode, COALESCE(SUM(f_balance), 0) AS balance
            FROM {table}
            WHERE d_balancedate = %s
              AND c_accountcode = '4001'
            GROUP BY c_projcode
            """,
            (date,),
        )
        self._fa4001_cache[date] = {
            str(row["c_projcode"]): to_decimal(row.get("balance"))
            for row in rows
        }
        return self._fa4001_cache[date]

    def get_ta_assetshare_sum(self, project_code: str, date: str) -> Decimal:
        table = qualified_name(self.config.business, "currency_report_duration")
        row = self.business_client.fetch_one(
            f"""
            SELECT COALESCE(SUM(f_assetshare), 0) AS assetshare_sum
            FROM {table}
            WHERE caldate = %s
              AND c_projectcode = %s
            """,
            (date, project_code),
        )
        return to_decimal(row["assetshare_sum"] if row else None)

    def get_valuation_asset_total(self, project_code: str, date: str) -> Decimal | None:
        return self._valuation_asset_totals_by_date(date).get(project_code)

    def _valuation_asset_totals_by_date(self, date: str) -> dict[str, Decimal]:
        if date in self._valuation_asset_total_cache:
            return self._valuation_asset_total_cache[date]

        table = qualified_name(self.config.dws, "fa_valuationreport_dws")
        rows = self.dws_client.fetch_all(
            f"""
            SELECT c_projcode, f_marketvalue
            FROM {table}
            WHERE d_valuationdate = %s
              AND c_accountcode = '0004'
            """,
            (date,),
        )
        totals: dict[str, Decimal] = {}
        for row in rows:
            project_code = str(row["c_projcode"])
            if project_code not in totals:
                totals[project_code] = to_decimal(row.get("f_marketvalue"))
        self._valuation_asset_total_cache[date] = totals
        return totals

    def list_valuation_leaf_rows(
        self,
        project_code: str,
        date: str,
        account_prefix: str | None = None,
    ) -> list[ValuationRow]:
        return self.list_valuation_rows(
            project_code,
            date,
            account_prefix=account_prefix,
            leaf_only=True,
        )

    def list_valuation_rows(
        self,
        project_code: str,
        date: str,
        account_prefix: str | None = None,
        exclude_prefix: str | None = None,
        leaf_only: bool = True,
    ) -> list[ValuationRow]:
        rows = list(self._valuation_rows_by_date(date).get(project_code, []))
        if account_prefix:
            rows = [row for row in rows if row.account_code.startswith(account_prefix)]
        if exclude_prefix:
            rows = [row for row in rows if not row.account_code.startswith(exclude_prefix)]
        if leaf_only:
            rows = [row for row in rows if row.account_code.count(".") == 4]
        return rows

    def _valuation_rows_by_date(self, date: str) -> dict[str, list[ValuationRow]]:
        if date in self._valuation_rows_cache:
            return self._valuation_rows_cache[date]

        table = qualified_name(self.config.dws, "fa_valuationreport_dws")
        rows = self.dws_client.fetch_all(
            f"""
            SELECT c_projcode, c_accountcode, c_accountname, f_marketvalue
            FROM {table}
            WHERE d_valuationdate = %s
              AND c_accountcode <> '0004'
            ORDER BY c_projcode, c_accountcode
            """,
            (date,),
        )
        grouped_rows: dict[str, list[ValuationRow]] = defaultdict(list)
        for row in rows:
            grouped_rows[str(row["c_projcode"])].append(
                ValuationRow(
                    account_code=str(row["c_accountcode"]),
                    account_name=str(row.get("c_accountname") or ""),
                    market_value=to_decimal(row.get("f_marketvalue")),
                )
            )
        self._valuation_rows_cache[date] = dict(grouped_rows)
        return self._valuation_rows_cache[date]

    def list_pact_assets(self, project_code: str, date: str, asset_name: str) -> list[PactAssetRow]:
        return self._pact_assets_by_date(date).get((project_code, asset_name), [])

    def list_project_pact_assets(self, project_code: str, date: str) -> list[PactAssetRow]:
        if date not in self._project_pact_asset_cache:
            grouped_assets: dict[str, list[PactAssetRow]] = defaultdict(list)
            for pact_assets in self._pact_assets_by_date(date).values():
                for pact_asset in pact_assets:
                    grouped_assets[pact_asset.project_code].append(pact_asset)
            self._project_pact_asset_cache[date] = dict(grouped_assets)
        return self._project_pact_asset_cache[date].get(project_code, [])

    def get_project_invest_balance(self, project_code: str, date: str, pact_id: str) -> Decimal | None:
        return self._project_invest_balances_by_date(date).get((project_code, pact_id))

    def get_ta_balance_totals(self, project_code: str, date: str) -> tuple[Decimal, Decimal]:
        if date not in self._ta_balance_totals_cache:
            self._ta_balance_totals_cache[date] = {}
        if project_code not in self._ta_balance_totals_cache[date]:
            self._ta_balance_totals_cache[date][project_code] = (
                self._dm_ta_balance_total(project_code, date),
                self._dws_ta_balance_total(project_code, date),
            )
        return self._ta_balance_totals_cache[date][project_code]

    def _dm_ta_balance_total(self, project_code: str, date: str) -> Decimal:
        table = TableRef(parts=("dm", "ta_pact_survamt_day_zgxg_dm")).quoted(self.config.dws.db_type)
        row = self.dws_client.fetch_one(
            f"""
            SELECT COALESCE(SUM(COALESCE(tpm_htincome, 0) + COALESCE(tpm_shareamt, 0)), 0) AS total
            FROM {table}
            WHERE tpm_date = %s
              AND tpm_tcmpcode = %s
            """,
            (date, project_code),
        )
        return to_decimal(row.get("total") if row else None)

    def _dws_ta_balance_total(self, project_code: str, date: str) -> Decimal:
        table = qualified_name(self.config.dws, "ta_pact_detail_dws")
        row = self.dws_client.fetch_one(
            f"""
            SELECT COALESCE(SUM(COALESCE(f_shareamt, 0) + COALESCE(f_alltincom, 0)), 0) AS total
            FROM {table}
            WHERE d_cldate = %s
              AND c_projcode = %s
            """,
            (date, project_code),
        )
        return to_decimal(row.get("total") if row else None)

    def list_blank_ta_client_type_rows(self, project_code: str, date: str) -> list[dict[str, Decimal | str]]:
        if date not in self._blank_ta_client_type_cache:
            self._blank_ta_client_type_cache[date] = {}
        if project_code in self._blank_ta_client_type_cache[date]:
            return self._blank_ta_client_type_cache[date][project_code]

        table = TableRef(parts=("dm", "ta_pact_survamt_day_zgxg_dm")).quoted(self.config.dws.db_type)
        rows = self.dws_client.fetch_all(
            f"""
            SELECT
                tpm_pactid,
                tpm_clientname,
                tpm_clientkind_tusp,
                tpm_clientkindex,
                tpm_spvtype,
                COALESCE(tpm_htincome, 0) AS tpm_htincome,
                COALESCE(tpm_shareamt, 0) AS tpm_shareamt,
                COALESCE(tpm_htincome, 0) + COALESCE(tpm_shareamt, 0) AS amount
            FROM {table}
            WHERE tpm_date = %s
              AND tpm_tcmpcode = %s
              AND COALESCE(tpm_htincome, 0) + COALESCE(tpm_shareamt, 0) <> 0
              AND (
                  tpm_clientkind_tusp IS NULL
                  OR TRIM(tpm_clientkind_tusp) = ''
                  OR (
                      tpm_clientkind_tusp = '4'
                      AND (tpm_clientkindex IS NULL OR TRIM(tpm_clientkindex) = '')
                  )
                  OR (
                      tpm_clientkind_tusp = '5'
                      AND (tpm_spvtype IS NULL OR TRIM(tpm_spvtype) = '')
                  )
              )
            ORDER BY tpm_pactid, tpm_clientname
            """,
            (date, project_code),
        )
        normalized_rows: list[dict[str, Decimal | str]] = [
            {
                "pact_id": str(row.get("tpm_pactid") or ""),
                "client_name": str(row.get("tpm_clientname") or ""),
                "client_kind": str(row.get("tpm_clientkind_tusp") or ""),
                "client_kind_index": str(row.get("tpm_clientkindex") or ""),
                "spv_type": str(row.get("tpm_spvtype") or ""),
                "ht_income": to_decimal(row.get("tpm_htincome")),
                "share_amount": to_decimal(row.get("tpm_shareamt")),
                "amount": to_decimal(row.get("amount")),
            }
            for row in rows
        ]
        self._blank_ta_client_type_cache[date][project_code] = normalized_rows
        return normalized_rows

    def get_security_balance_refinement(
        self,
        project_code: str,
        date: str,
        stock_code: str,
        security_name: str,
    ) -> dict[str, Decimal | str] | None:
        table = TableRef(parts=("dm", "fa_security_balance_zgxg_dm")).quoted(self.config.dws.db_type)
        row = self.dws_client.fetch_one(
            f"""
            SELECT sbm_seclas_h2024, sbm_gpgqtype_h, sbm_fundtype
            FROM {table}
            WHERE sbm_projcode = %s
              AND sbm_cacldate = %s
              AND sbm_stockcode = %s
              AND sbm_sename = %s
              AND COALESCE(sbm_balamoney_cost, 0) + COALESCE(sbm_balamoney_fair, 0) + COALESCE(sbm_balamoney_inte, 0) <> 0
            """,
            (project_code, date, stock_code, security_name),
        )
        return dict(row) if row else None

    def list_security_balance_amounts(self, project_code: str, date: str) -> list[dict[str, Decimal | str]]:
        table = TableRef(parts=("dm", "fa_security_balance_zgxg_dm")).quoted(self.config.dws.db_type)
        rows = self.dws_client.fetch_all(
            f"""
            SELECT
                sbm_stockcode AS stock_code,
                sbm_sename AS security_name,
                SUM(COALESCE(sbm_balamoney_cost, 0) + COALESCE(sbm_balamoney_fair, 0) + COALESCE(sbm_balamoney_inte, 0)) AS amount
            FROM {table}
            WHERE sbm_projcode = %s
              AND sbm_cacldate = %s
            GROUP BY sbm_stockcode, sbm_sename
            HAVING SUM(COALESCE(sbm_balamoney_cost, 0) + COALESCE(sbm_balamoney_fair, 0) + COALESCE(sbm_balamoney_inte, 0)) <> 0
            """,
            (project_code, date),
        )
        return [dict(row) for row in rows]

    def get_dm_project_invest_refinement(self, project_code: str, date: str, pact_id: str) -> dict[str, Decimal | str] | None:
        table = TableRef(parts=("dm", "am_projinvest_zgxg_dm")).quoted(self.config.dws.db_type)
        row = self.dws_client.fetch_one(
            f"""
            SELECT pin_acbalance, pin_gqtype_h
            FROM {table}
            WHERE pin_projcode = %s
              AND pin_cldate = %s
              AND pin_mpactid = %s
              AND COALESCE(pin_acbalance, 0) <> 0
            """,
            (project_code, date, pact_id),
        )
        return dict(row) if row else None

    def get_dm_project_invest_contract_balance(self, project_code: str, date: str, pact_id: str) -> dict[str, Decimal | str] | None:
        table = TableRef(parts=("dm", "am_projinvest_zgxg_dm")).quoted(self.config.dws.db_type)
        row = self.dws_client.fetch_one(
            f"""
            SELECT pin_acbalance
            FROM {table}
            WHERE pin_projcode = %s
              AND pin_cldate = %s
              AND pin_mpactid = %s
            """,
            (project_code, date, pact_id),
        )
        return dict(row) if row else None

    def get_spv_project_invest_refinement(self, project_code: str, date: str, pact_id: str) -> dict[str, Decimal | str] | None:
        table = TableRef(parts=("dm", "am_projinvest_spv_zgxg_dm")).quoted(self.config.dws.db_type)
        row = self.dws_client.fetch_one(
            f"""
            SELECT svd_assettype
            FROM {table}
            WHERE svd_projcode = %s
              AND svd_cldate = %s
              AND svd_mpactid = %s
              AND COALESCE(svd_balamoney_cost, 0) + COALESCE(svd_balamoney_inte, 0) + COALESCE(svd_balamoney_fair, 0) <> 0
            """,
            (project_code, date, pact_id),
        )
        return dict(row) if row else None

    def get_property_right_refinement(self, project_code: str, pact_id: str) -> dict[str, Decimal | str] | None:
        table = TableRef(parts=("zgxg_zhbs", "ccqxx")).quoted(self.config.dws.db_type)
        row = self.dws_client.fetch_one(
            f"""
            SELECT pin_acbalance
            FROM {table}
            WHERE pjdw_projcode = %s
              AND pin_mpactid = %s
              AND COALESCE(pin_acbalance, 0) <> 0
            """,
            (project_code, pact_id),
        )
        return dict(row) if row else None

    def has_report_rows(self, table_parts: tuple[str, ...], date: str) -> bool:
        table = TableRef(parts=table_parts).quoted(self.config.business.db_type)
        row = self.business_client.fetch_one(
            f"""
            SELECT 1 AS exists_flag
            FROM {table}
            WHERE caldate = %s
            LIMIT 1
            """,
            (date,),
        )
        return row is not None

    def has_reverse_repo_blank_rows(self, project_code: str) -> bool:
        table = TableRef(parts=("assman_reg", "ex_pledge_back")).quoted(self.config.business.db_type)
        row = self.business_client.fetch_one(
            f"""
            SELECT 1 AS exists_flag
            FROM {table}
            WHERE project_code = %s
              AND subcode LIKE %s
              AND (buyback_money IS NULL OR expenses IS NULL)
            LIMIT 1
            """,
            (project_code, "7%"),
        )
        return row is not None

    def get_reverse_repo_business_amount(self, project_code: str) -> Decimal:
        return self._get_repo_business_amount(
            project_code,
            subcode_prefix="7%",
            amount_expression="COALESCE(buyback_money, 0) + COALESCE(expenses, 0)",
        )

    def get_positive_repo_business_amount(self, project_code: str) -> Decimal:
        return self._get_repo_business_amount(
            project_code,
            subcode_prefix="8%",
            amount_expression="COALESCE(buyback_money, 0) - COALESCE(expenses, 0)",
        )

    def _get_repo_business_amount(self, project_code: str, *, subcode_prefix: str, amount_expression: str) -> Decimal:
        table = TableRef(parts=("assman_reg", "ex_pledge_back")).quoted(self.config.business.db_type)
        row = self.business_client.fetch_one(
            f"""
            SELECT COALESCE(SUM({amount_expression}), 0) AS amount
            FROM {table}
            WHERE project_code = %s
              AND subcode LIKE %s
            """,
            (project_code, subcode_prefix),
        )
        return to_decimal(row.get("amount") if row else None)

    def _project_invest_balances_by_date(self, date: str) -> dict[tuple[str, str], Decimal]:
        if date in self._project_invest_balance_cache:
            return self._project_invest_balance_cache[date]

        table = qualified_name(self.config.dws, "am_projinvest_dws")
        rows = self.dws_client.fetch_all(
            f"""
            SELECT c_projcode, c_pactid, COALESCE(SUM(f_acbalance), 0) AS acbalance
            FROM {table}
            WHERE d_cldate = %s
            GROUP BY c_projcode, c_pactid
            """,
            (date,),
        )
        self._project_invest_balance_cache[date] = {
            (str(row["c_projcode"]), str(row.get("c_pactid") or "")): to_decimal(row.get("acbalance"))
            for row in rows
        }
        return self._project_invest_balance_cache[date]

    def _pact_assets_by_date(self, date: str) -> dict[tuple[str, str], list[PactAssetRow]]:
        if date in self._pact_asset_cache:
            return self._pact_asset_cache[date]

        table = qualified_name(self.config.dws, "am_pactasset_dws")
        rows = self.dws_client.fetch_all(
            f"""
            SELECT c_projcode, c_udlyasset, c_stockcode, c_pactid, c_spv_type, c_assettype
            FROM {table}
            WHERE d_cldate = %s
            """,
            (date,),
        )
        grouped_assets: dict[tuple[str, str], list[PactAssetRow]] = defaultdict(list)
        for row in rows:
            pact_asset = PactAssetRow(
                project_code=str(row["c_projcode"]),
                asset_name=str(row.get("c_udlyasset") or ""),
                stock_code=str(row.get("c_stockcode") or ""),
                pact_id=str(row.get("c_pactid") or ""),
                spv_type=str(row.get("c_spv_type") or ""),
                asset_type=str(row.get("c_assettype") or ""),
            )
            grouped_assets[(pact_asset.project_code, pact_asset.asset_name)].append(pact_asset)
        self._pact_asset_cache[date] = dict(grouped_assets)
        return self._pact_asset_cache[date]
