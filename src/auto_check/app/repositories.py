from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import re
import unicodedata

from auto_check.app.config import AppConfig, DataSourceConfig
from auto_check.app.db import DatabaseClient, qualified_name
from auto_check.app.pbc_import import TableRef
from auto_check.app.reconcile_schema import (
    ReconcileSchemaSettings,
    ReconcileSourceRef,
    ReconcileTableSchema,
    safe_column_name,
    safe_table_ref,
)
from auto_check.engine.models import PactAssetRow, ProjectBalance, ValuationRow
from auto_check.engine.money import to_decimal


DEFAULT_RECONCILE_TABLES: dict[str, ReconcileTableSchema] = {
    "zf_detail": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="business", name="报表库", match_by="id_then_name"),
        table="zf_detail_2024",
        display_name="资负报表主表",
        fields={
            "check_date": "caldate",
            "project_code": "projinnercode",
            "project_name": "projname",
            "asset_total": "a0001",
            "liability_equity_total": "d0000",
            "received_trust_balance": "c1000",
        },
    ),
    "fa_account_balance": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="fa_accountbalance_dws",
        display_name="FA 科目余额表",
        fields={
            "project_code": "c_projcode",
            "balance_date": "d_balancedate",
            "account_code": "c_accountcode",
            "account_name": "c_accountname",
            "balance": "f_balance",
        },
    ),
    "fa_valuation": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="fa_valuationreport_dws",
        display_name="FA 估值表",
        fields={
            "project_code": "c_projcode",
            "valuation_date": "d_valuationdate",
            "account_code": "c_accountcode",
            "account_name": "c_accountname",
            "market_value": "f_marketvalue",
        },
    ),
    "am_pact_asset": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="am_pactasset_dws",
        display_name="AM 标的表",
        fields={
            "project_code": "c_projcode",
            "close_date": "d_cldate",
            "asset_name": "c_udlyasset",
            "stock_code": "c_stockcode",
            "pact_id": "c_pactid",
            "spv_type": "c_spv_type",
            "asset_type": "c_assettype",
            "data_source": "c_datasource",
        },
    ),
    "am_project_invest": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="am_projinvest_dws",
        display_name="AM 合同投融资余额表",
        fields={
            "project_code": "c_projcode",
            "close_date": "d_cldate",
            "pact_id": "c_pactid",
            "invest_balance": "f_acbalance",
            "contract_start_date": "d_bdate",
        },
    ),
    "ta_pact_detail": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="ta_pact_detail_dws",
        display_name="DWS TA 合同明细表",
        fields={
            "project_code": "c_projcode",
            "close_date": "d_cldate",
            "share_amount": "f_shareamt",
            "all_income": "f_alltincom",
        },
    ),
    "ta_survamt_dm": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="dm.ta_pact_survamt_day_zgxg_dm",
        display_name="DM TA 存续金额表",
        fields={
            "check_date": "tpm_date",
            "project_code": "tpm_tcmpcode",
            "pact_id": "tpm_pactid",
            "client_name": "tpm_clientname",
            "client_kind": "tpm_clientkind_tusp",
            "client_kind_index": "tpm_clientkindex",
            "spv_type": "tpm_spvtype",
            "ht_income": "tpm_htincome",
            "share_amount": "tpm_shareamt",
        },
    ),
    "fa_security_balance_dm": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="dm.fa_security_balance_zgxg_dm",
        display_name="DM FA 证券余额表",
        fields={
            "project_code": "sbm_projcode",
            "check_date": "sbm_cacldate",
            "stock_code": "sbm_stockcode",
            "security_name": "sbm_sename",
            "bond_category": "sbm_seclas_h2024",
            "stock_equity_category": "sbm_gpgqtype_h",
            "fund_type": "sbm_fundtype",
            "balance_cost": "sbm_balamoney_cost",
            "balance_fair": "sbm_balamoney_fair",
            "balance_interest": "sbm_balamoney_inte",
        },
    ),
    "dm_project_invest": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="dm.am_projinvest_zgxg_dm",
        display_name="DM AM 投融资余额表",
        fields={
            "project_code": "pin_projcode",
            "close_date": "pin_cldate",
            "pact_id": "pin_mpactid",
            "invest_balance": "pin_acbalance",
            "equity_invest_type": "pin_gqtype_h",
        },
    ),
    "dm_spv_project_invest": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="dm.am_projinvest_spv_zgxg_dm",
        display_name="DM AM SPV 投融资余额表",
        fields={
            "project_code": "svd_projcode",
            "close_date": "svd_cldate",
            "pact_id": "svd_mpactid",
            "asset_type": "svd_assettype",
            "balance_cost": "svd_balamoney_cost",
            "balance_interest": "svd_balamoney_inte",
            "balance_fair": "svd_balamoney_fair",
        },
    ),
    "property_right_contract": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
        table="zgxg_zhbs.ccqxx",
        display_name="财产权合同信息表",
        fields={
            "project_code": "pjdw_projcode",
            "pact_id": "pin_mpactid",
            "invest_balance": "pin_acbalance",
        },
    ),
    "pledge_back": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="business", name="报表库", match_by="id_then_name"),
        table="ass_man_reg.ex_pledge_back",
        display_name="回购质押明细表",
        fields={
            "project_code": "project_code",
            "subject_code": "subcode",
            "buyback_money": "buyback_money",
            "expenses": "expenses",
        },
    ),
    "ta_asset_share_duration": ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="business", name="报表库", match_by="id_then_name"),
        table="currency_report_duration",
        display_name="TA 份额本地测试表",
        fields={
            "check_date": "caldate",
            "project_code": "c_projectcode",
            "asset_share": "f_assetshare",
        },
    ),
}

for _report_key, _report_table, _report_name in (
    ("report_detail_2_1_2", "currency_report_24.currency_detail_project_2_1_2", "资负数据子系统-贷款明细表"),
    ("report_detail_2_1_4", "currency_report_24.currency_detail_project_2_1_4", "资负数据子系统-债务证券明细表"),
    ("report_detail_2_1_5", "currency_report_24.currency_detail_project_2_1_5", "资负数据子系统-股票股权明细表"),
    ("report_detail_2_1_5_2", "currency_report_24.currency_detail_project_2_1_5_2", "资负数据子系统-股权投资明细表"),
    ("report_detail_2_1_6", "currency_report_24.currency_detail_project_2_1_6", "资负数据子系统-特定目的载体明细表"),
    ("report_detail_2_1_8", "currency_report_24.currency_detail_project_2_1_8", "资负数据子系统-实收信托明细表"),
    ("report_detail_2_1_9", "currency_report_24.currency_detail_project_2_1_9", "资负数据子系统-其他债权明细表"),
):
    DEFAULT_RECONCILE_TABLES[_report_key] = ReconcileTableSchema(
        source_ref=ReconcileSourceRef(id="business", name="报表库", match_by="id_then_name"),
        table=_report_table,
        display_name=_report_name,
        fields={"check_date": "caldate"},
    )

REPORT_TABLE_KEYS = {
    ("currency_report_24", "currency_detail_project_2_1_2"): "report_detail_2_1_2",
    ("currency_report_24", "currency_detail_project_2_1_4"): "report_detail_2_1_4",
    ("currency_report_24", "currency_detail_project_2_1_5"): "report_detail_2_1_5",
    ("currency_report_24", "currency_detail_project_2_1_5_2"): "report_detail_2_1_5_2",
    ("currency_report_24", "currency_detail_project_2_1_6"): "report_detail_2_1_6",
    ("currency_report_24", "currency_detail_project_2_1_8"): "report_detail_2_1_8",
    ("currency_report_24", "currency_detail_project_2_1_9"): "report_detail_2_1_9",
}


class AutoCheckRepository:
    def __init__(
        self,
        config: AppConfig,
        *,
        dws_client: DatabaseClient | None = None,
        business_client: DatabaseClient | None = None,
        schema: ReconcileSchemaSettings | None = None,
        source_configs: dict[str, DataSourceConfig] | None = None,
        source_clients: dict[str, DatabaseClient] | None = None,
    ):
        self.config = config
        self.dws_client = dws_client or DatabaseClient(config.dws)
        self.business_client = business_client or DatabaseClient(config.business)
        self.schema = schema or ReconcileSchemaSettings()
        self._source_configs: dict[str, DataSourceConfig] = {
            "dws": config.dws,
            "business": config.business,
        }
        if source_configs:
            self._source_configs.update({key: value for key, value in source_configs.items() if key})
        self._source_clients: dict[str, DatabaseClient] = {
            "dws": self.dws_client,
            "business": self.business_client,
        }
        if source_clients:
            self._source_clients.update({key: value for key, value in source_clients.items() if key})
        self._owned_source_clients: dict[str, DatabaseClient] = {}
        self._fa4001_cache: dict[str, dict[str, Decimal]] = {}
        self._valuation_asset_total_cache: dict[str, dict[str, Decimal]] = {}
        self._valuation_rows_cache: dict[str, dict[str, list[ValuationRow]]] = {}
        self._pact_asset_cache: dict[str, dict[tuple[str, str], list[PactAssetRow]]] = {}
        self._project_pact_asset_cache: dict[str, dict[str, list[PactAssetRow]]] = {}
        self._project_invest_balance_cache: dict[str, dict[tuple[str, str], Decimal]] = {}
        self._project_invest_contract_start_cache: dict[str, dict[tuple[str, str], str]] = {}
        self._ta_balance_totals_cache: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
        self._blank_ta_client_type_cache: dict[str, dict[str, list[dict[str, Decimal | str]]]] = {}

    def _table_schema(self, logical_key: str) -> ReconcileTableSchema:
        default = DEFAULT_RECONCILE_TABLES[logical_key]
        override = self.schema.tables.get(logical_key) if self.schema.tables else None
        if self.schema.strict:
            if override is None:
                raise ValueError(f"自动对账表配置缺少逻辑表: {logical_key}")
            if not override.table:
                raise ValueError(f"自动对账表配置缺少表名: {logical_key}")
            if not (override.source_ref.id or override.source_ref.name):
                raise ValueError(f"自动对账表配置缺少数据源: {logical_key}")
            return override
        if override is None:
            return default
        return ReconcileTableSchema(
            source_ref=override.source_ref
            if (override.source_ref.id or override.source_ref.name)
            else default.source_ref,
            table=override.table or default.table,
            display_name=override.display_name or default.display_name,
            fields={**default.fields, **override.fields},
            optional_fields={**default.optional_fields, **override.optional_fields},
        )

    def _source_key(self, table_schema: ReconcileTableSchema) -> str:
        source_ref = table_schema.source_ref
        candidates: list[str] = []
        source_id = str(source_ref.id or "").strip()
        source_name = str(source_ref.name or "").strip()
        if source_id:
            candidates.append(source_id)
        if source_ref.match_by != "id_only" and source_name:
            candidates.append(source_name)
        for candidate in candidates:
            if candidate in self._source_clients or candidate in self._source_configs:
                return candidate
        if source_id in ("dws", "business"):
            return source_id
        raise ValueError(f"自动对账表配置的数据源不存在: {source_id or source_name}")

    def _client_and_config(self, logical_key: str) -> tuple[DatabaseClient, DataSourceConfig]:
        table_schema = self._table_schema(logical_key)
        source_key = self._source_key(table_schema)
        config = self._source_configs.get(source_key)
        client = self._source_clients.get(source_key)
        if client is None:
            if config is None:
                raise ValueError(f"自动对账表配置的数据源不存在: {source_key}")
            client = self._owned_source_clients.setdefault(source_key, DatabaseClient(config))
            self._source_clients[source_key] = client
        if config is None:
            config = getattr(client, "config", None)
        if config is None:
            config = self.config.dws if source_key == "dws" else self.config.business
        return client, config

    def _client_table(self, logical_key: str) -> tuple[DatabaseClient, str]:
        table_schema = self._table_schema(logical_key)
        client, config = self._client_and_config(logical_key)
        table_ref = safe_table_ref(table_schema.table)
        if len(table_ref.parts) == 1:
            return client, qualified_name(config, table_ref.parts[0])
        return client, table_ref.quoted(config.db_type)

    def _field(self, logical_key: str, field_key: str, *, optional: bool = False) -> str | None:
        table_schema = self._table_schema(logical_key)
        physical = table_schema.fields.get(field_key)
        if physical is None:
            physical = table_schema.optional_fields.get(field_key)
        if physical is None:
            if optional:
                return None
            raise ValueError(f"自动对账表配置缺少字段: {logical_key}.{field_key}")
        return safe_column_name(physical)

    def _col(self, logical_key: str, field_key: str, *, alias: str | None = None, optional: bool = False) -> str | None:
        field = self._field(logical_key, field_key, optional=optional)
        if field is None:
            return None
        return f"{alias}.{field}" if alias else field

    def _select_as(self, logical_key: str, field_key: str, output_name: str, *, alias: str | None = None) -> str:
        return f"{self._col(logical_key, field_key, alias=alias)} AS {output_name}"

    def _amount_expression(self, logical_key: str, *field_keys: str, alias: str | None = None, sign: int = 1) -> str:
        parts = [f"COALESCE({self._col(logical_key, field_key, alias=alias)}, 0)" for field_key in field_keys]
        operator = " + " if sign >= 0 else " - "
        return operator.join(parts)

    def list_project_balances(self, date: str) -> list[ProjectBalance]:
        client, table = self._client_table("zf_detail")
        check_date = self._field("zf_detail", "check_date")
        project_code = self._field("zf_detail", "project_code")
        project_name = self._field("zf_detail", "project_name")
        asset_total = self._field("zf_detail", "asset_total")
        liability_equity_total = self._field("zf_detail", "liability_equity_total")
        received_trust_balance = self._field("zf_detail", "received_trust_balance")
        rows = client.fetch_all(
            f"""
            SELECT
                {project_code} AS projinnercode,
                {project_name} AS projname,
                {asset_total} AS a0001,
                {liability_equity_total} AS d0000,
                {received_trust_balance} AS c1000
            FROM {table}
            WHERE {check_date} = %s
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

        client, table = self._client_table("fa_account_balance")
        project_code = self._field("fa_account_balance", "project_code")
        balance_date = self._field("fa_account_balance", "balance_date")
        account_code = self._field("fa_account_balance", "account_code")
        balance = self._field("fa_account_balance", "balance")
        rows = client.fetch_all(
            f"""
            SELECT {project_code} AS c_projcode, COALESCE(SUM({balance}), 0) AS balance
            FROM {table}
            WHERE {balance_date} = %s
              AND {account_code} = '4001'
            GROUP BY {project_code}
            """,
            (date,),
        )
        self._fa4001_cache[date] = {
            str(row["c_projcode"]): to_decimal(row.get("balance"))
            for row in rows
        }
        return self._fa4001_cache[date]

    def get_ta_assetshare_sum(self, project_code: str, date: str) -> Decimal:
        client, table = self._client_table("ta_asset_share_duration")
        check_date = self._field("ta_asset_share_duration", "check_date")
        project_code_field = self._field("ta_asset_share_duration", "project_code")
        asset_share = self._field("ta_asset_share_duration", "asset_share")
        row = client.fetch_one(
            f"""
            SELECT COALESCE(SUM({asset_share}), 0) AS assetshare_sum
            FROM {table}
            WHERE {check_date} = %s
              AND {project_code_field} = %s
            """,
            (date, project_code),
        )
        return to_decimal(row["assetshare_sum"] if row else None)

    def get_valuation_asset_total(self, project_code: str, date: str) -> Decimal | None:
        return self._valuation_asset_totals_by_date(date).get(project_code)

    def _valuation_asset_totals_by_date(self, date: str) -> dict[str, Decimal]:
        if date in self._valuation_asset_total_cache:
            return self._valuation_asset_total_cache[date]

        client, table = self._client_table("fa_valuation")
        project_code = self._field("fa_valuation", "project_code")
        valuation_date = self._field("fa_valuation", "valuation_date")
        account_code = self._field("fa_valuation", "account_code")
        market_value = self._field("fa_valuation", "market_value")
        rows = client.fetch_all(
            f"""
            SELECT {project_code} AS c_projcode, {market_value} AS f_marketvalue
            FROM {table}
            WHERE {valuation_date} = %s
              AND {account_code} = '0004'
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

        client, table = self._client_table("fa_valuation")
        project_code = self._field("fa_valuation", "project_code")
        valuation_date = self._field("fa_valuation", "valuation_date")
        account_code = self._field("fa_valuation", "account_code")
        account_name = self._field("fa_valuation", "account_name")
        market_value = self._field("fa_valuation", "market_value")
        rows = client.fetch_all(
            f"""
            SELECT
                {project_code} AS c_projcode,
                {account_code} AS c_accountcode,
                {account_name} AS c_accountname,
                {market_value} AS f_marketvalue
            FROM {table}
            WHERE {valuation_date} = %s
              AND {account_code} <> '0004'
            ORDER BY {project_code}, {account_code}
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
        client, table = self._client_table("ta_survamt_dm")
        check_date = self._field("ta_survamt_dm", "check_date")
        project_code_field = self._field("ta_survamt_dm", "project_code")
        amount_expression = self._amount_expression("ta_survamt_dm", "ht_income", "share_amount")
        row = client.fetch_one(
            f"""
            SELECT COALESCE(SUM({amount_expression}), 0) AS total
            FROM {table}
            WHERE {check_date} = %s
              AND {project_code_field} = %s
            """,
            (date, project_code),
        )
        return to_decimal(row.get("total") if row else None)

    def _dws_ta_balance_total(self, project_code: str, date: str) -> Decimal:
        client, table = self._client_table("ta_pact_detail")
        close_date = self._field("ta_pact_detail", "close_date")
        project_code_field = self._field("ta_pact_detail", "project_code")
        amount_expression = self._amount_expression("ta_pact_detail", "share_amount", "all_income")
        row = client.fetch_one(
            f"""
            SELECT COALESCE(SUM({amount_expression}), 0) AS total
            FROM {table}
            WHERE {close_date} = %s
              AND {project_code_field} = %s
            """,
            (date, project_code),
        )
        return to_decimal(row.get("total") if row else None)

    def list_blank_ta_client_type_rows(self, project_code: str, date: str) -> list[dict[str, Decimal | str]]:
        if date not in self._blank_ta_client_type_cache:
            self._blank_ta_client_type_cache[date] = {}
        if project_code in self._blank_ta_client_type_cache[date]:
            return self._blank_ta_client_type_cache[date][project_code]

        client, table = self._client_table("ta_survamt_dm")
        check_date = self._field("ta_survamt_dm", "check_date")
        project_code_field = self._field("ta_survamt_dm", "project_code")
        pact_id = self._field("ta_survamt_dm", "pact_id")
        client_name = self._field("ta_survamt_dm", "client_name")
        client_kind = self._field("ta_survamt_dm", "client_kind")
        client_kind_index = self._field("ta_survamt_dm", "client_kind_index")
        spv_type = self._field("ta_survamt_dm", "spv_type")
        ht_income = self._field("ta_survamt_dm", "ht_income")
        share_amount = self._field("ta_survamt_dm", "share_amount")
        amount_expression = self._amount_expression("ta_survamt_dm", "ht_income", "share_amount")
        rows = client.fetch_all(
            f"""
            SELECT
                {pact_id} AS tpm_pactid,
                {client_name} AS tpm_clientname,
                {client_kind} AS tpm_clientkind_tusp,
                {client_kind_index} AS tpm_clientkindex,
                {spv_type} AS tpm_spvtype,
                COALESCE({ht_income}, 0) AS tpm_htincome,
                COALESCE({share_amount}, 0) AS tpm_shareamt,
                {amount_expression} AS amount
            FROM {table}
            WHERE {check_date} = %s
              AND {project_code_field} = %s
              AND {amount_expression} <> 0
              AND (
                  {client_kind} IS NULL
                  OR TRIM({client_kind}) = ''
                  OR (
                      {client_kind} = '4'
                      AND ({client_kind_index} IS NULL OR TRIM({client_kind_index}) = '')
                  )
                  OR (
                      {client_kind} = '5'
                      AND ({spv_type} IS NULL OR TRIM({spv_type}) = '')
                  )
              )
            ORDER BY {pact_id}, {client_name}
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
        client, table = self._client_table("fa_security_balance_dm")
        project_code_field = self._field("fa_security_balance_dm", "project_code")
        check_date = self._field("fa_security_balance_dm", "check_date")
        stock_code_field = self._field("fa_security_balance_dm", "stock_code")
        security_name_field = self._field("fa_security_balance_dm", "security_name")
        bond_category = self._field("fa_security_balance_dm", "bond_category")
        stock_equity_category = self._field("fa_security_balance_dm", "stock_equity_category")
        fund_type = self._field("fa_security_balance_dm", "fund_type")
        amount_expression = self._amount_expression(
            "fa_security_balance_dm",
            "balance_cost",
            "balance_fair",
            "balance_interest",
        )
        row = client.fetch_one(
            f"""
            SELECT
                {bond_category} AS sbm_seclas_h2024,
                {stock_equity_category} AS sbm_gpgqtype_h,
                {fund_type} AS sbm_fundtype
            FROM {table}
            WHERE {project_code_field} = %s
              AND {check_date} = %s
              AND {stock_code_field} = %s
              AND {security_name_field} = %s
              AND {amount_expression} <> 0
            """,
            (project_code, date, stock_code, security_name),
        )
        return dict(row) if row else None

    def list_security_balance_amounts(self, project_code: str, date: str) -> list[dict[str, Decimal | str]]:
        client, table = self._client_table("fa_security_balance_dm")
        project_code_field = self._field("fa_security_balance_dm", "project_code")
        check_date = self._field("fa_security_balance_dm", "check_date")
        stock_code_field = self._field("fa_security_balance_dm", "stock_code")
        security_name_field = self._field("fa_security_balance_dm", "security_name")
        amount_expression = self._amount_expression(
            "fa_security_balance_dm",
            "balance_cost",
            "balance_fair",
            "balance_interest",
        )
        rows = client.fetch_all(
            f"""
            SELECT
                {stock_code_field} AS stock_code,
                {security_name_field} AS security_name,
                SUM({amount_expression}) AS amount
            FROM {table}
            WHERE {project_code_field} = %s
              AND {check_date} = %s
            GROUP BY {stock_code_field}, {security_name_field}
            HAVING SUM({amount_expression}) <> 0
            """,
            (project_code, date),
        )
        return [dict(row) for row in rows]

    def get_dm_project_invest_refinement(self, project_code: str, date: str, pact_id: str) -> dict[str, Decimal | str] | None:
        client, table = self._client_table("dm_project_invest")
        project_code_field = self._field("dm_project_invest", "project_code")
        close_date = self._field("dm_project_invest", "close_date")
        pact_id_field = self._field("dm_project_invest", "pact_id")
        invest_balance = self._field("dm_project_invest", "invest_balance")
        equity_invest_type = self._field("dm_project_invest", "equity_invest_type")
        row = client.fetch_one(
            f"""
            SELECT {invest_balance} AS pin_acbalance, {equity_invest_type} AS pin_gqtype_h
            FROM {table}
            WHERE {project_code_field} = %s
              AND {close_date} = %s
              AND {pact_id_field} = %s
              AND COALESCE({invest_balance}, 0) <> 0
            """,
            (project_code, date, pact_id),
        )
        return dict(row) if row else None

    def get_dm_project_invest_contract_balance(self, project_code: str, date: str, pact_id: str) -> dict[str, Decimal | str] | None:
        client, table = self._client_table("dm_project_invest")
        project_code_field = self._field("dm_project_invest", "project_code")
        close_date = self._field("dm_project_invest", "close_date")
        pact_id_field = self._field("dm_project_invest", "pact_id")
        invest_balance = self._field("dm_project_invest", "invest_balance")
        row = client.fetch_one(
            f"""
            SELECT {invest_balance} AS pin_acbalance
            FROM {table}
            WHERE {project_code_field} = %s
              AND {close_date} = %s
              AND {pact_id_field} = %s
            """,
            (project_code, date, pact_id),
        )
        return dict(row) if row else None

    def get_spv_project_invest_refinement(self, project_code: str, date: str, pact_id: str) -> dict[str, Decimal | str] | None:
        client, table = self._client_table("dm_spv_project_invest")
        project_code_field = self._field("dm_spv_project_invest", "project_code")
        close_date = self._field("dm_spv_project_invest", "close_date")
        pact_id_field = self._field("dm_spv_project_invest", "pact_id")
        asset_type = self._field("dm_spv_project_invest", "asset_type")
        amount_expression = self._amount_expression(
            "dm_spv_project_invest",
            "balance_cost",
            "balance_interest",
            "balance_fair",
        )
        row = client.fetch_one(
            f"""
            SELECT {asset_type} AS svd_assettype
            FROM {table}
            WHERE {project_code_field} = %s
              AND {close_date} = %s
              AND {pact_id_field} = %s
              AND {amount_expression} <> 0
            """,
            (project_code, date, pact_id),
        )
        return dict(row) if row else None

    def get_property_right_refinement(self, project_code: str, pact_id: str) -> dict[str, Decimal | str] | None:
        client, table = self._client_table("property_right_contract")
        project_code_field = self._field("property_right_contract", "project_code")
        pact_id_field = self._field("property_right_contract", "pact_id")
        invest_balance = self._field("property_right_contract", "invest_balance")
        row = client.fetch_one(
            f"""
            SELECT {invest_balance} AS pin_acbalance
            FROM {table}
            WHERE {project_code_field} = %s
              AND {pact_id_field} = %s
              AND COALESCE({invest_balance}, 0) <> 0
            """,
            (project_code, pact_id),
        )
        return dict(row) if row else None

    def has_report_rows(self, table_parts: tuple[str, ...], date: str) -> bool:
        logical_key = REPORT_TABLE_KEYS.get(table_parts, ".".join(table_parts))
        client, table = self._client_table(logical_key)
        check_date = self._field(logical_key, "check_date")
        row = client.fetch_one(
            f"""
            SELECT 1 AS exists_flag
            FROM {table}
            WHERE {check_date} = %s
            LIMIT 1
            """,
            (date,),
        )
        return row is not None

    def count_report_project_name_matches_without_chinese_parentheses(self, date: str, normalized_name: str) -> int:
        target_name = _normalize_report_project_name_without_chinese_parentheses(normalized_name)
        if not target_name:
            return 0

        client, table = self._client_table("zf_detail")
        check_date = self._field("zf_detail", "check_date")
        project_name = self._field("zf_detail", "project_name")
        rows = client.fetch_all(
            f"""
            SELECT {project_name} AS projname
            FROM {table}
            WHERE {check_date} = %s
            """,
            (date,),
        )
        count = 0
        for row in rows:
            candidate_name = _normalize_report_project_name_without_chinese_parentheses(str(row.get("projname") or ""))
            if candidate_name and (target_name in candidate_name or candidate_name in target_name):
                count += 1
        return count

    def has_reverse_repo_blank_rows(self, project_code: str) -> bool:
        client, table = self._client_table("pledge_back")
        project_code_field = self._field("pledge_back", "project_code")
        subject_code = self._field("pledge_back", "subject_code")
        buyback_money = self._field("pledge_back", "buyback_money")
        expenses = self._field("pledge_back", "expenses")
        row = client.fetch_one(
            f"""
            SELECT 1 AS exists_flag
            FROM {table}
            WHERE {project_code_field} = %s
              AND {subject_code} LIKE %s
              AND ({buyback_money} IS NULL OR {expenses} IS NULL)
            LIMIT 1
            """,
            (project_code, "7%"),
        )
        return row is not None

    def get_reverse_repo_business_amount(self, project_code: str) -> Decimal:
        buyback_money = self._field("pledge_back", "buyback_money")
        expenses = self._field("pledge_back", "expenses")
        return self._get_repo_business_amount(
            project_code,
            subcode_prefix="7%",
            amount_expression=f"COALESCE({buyback_money}, 0) + COALESCE({expenses}, 0)",
        )

    def get_positive_repo_business_amount(self, project_code: str) -> Decimal:
        buyback_money = self._field("pledge_back", "buyback_money")
        expenses = self._field("pledge_back", "expenses")
        return self._get_repo_business_amount(
            project_code,
            subcode_prefix="8%",
            amount_expression=f"COALESCE({buyback_money}, 0) - COALESCE({expenses}, 0)",
        )

    def _get_repo_business_amount(self, project_code: str, *, subcode_prefix: str, amount_expression: str) -> Decimal:
        client, table = self._client_table("pledge_back")
        project_code_field = self._field("pledge_back", "project_code")
        subject_code = self._field("pledge_back", "subject_code")
        row = client.fetch_one(
            f"""
            SELECT COALESCE(SUM({amount_expression}), 0) AS amount
            FROM {table}
            WHERE {project_code_field} = %s
              AND {subject_code} LIKE %s
            """,
            (project_code, subcode_prefix),
        )
        return to_decimal(row.get("amount") if row else None)

    def _project_invest_balances_by_date(self, date: str) -> dict[tuple[str, str], Decimal]:
        if date in self._project_invest_balance_cache:
            return self._project_invest_balance_cache[date]

        client, table = self._client_table("am_project_invest")
        project_code = self._field("am_project_invest", "project_code")
        close_date = self._field("am_project_invest", "close_date")
        pact_id = self._field("am_project_invest", "pact_id")
        invest_balance = self._field("am_project_invest", "invest_balance")
        rows = client.fetch_all(
            f"""
            SELECT
                {project_code} AS c_projcode,
                {pact_id} AS c_pactid,
                COALESCE(SUM({invest_balance}), 0) AS acbalance
            FROM {table}
            WHERE {close_date} = %s
            GROUP BY {project_code}, {pact_id}
            """,
            (date,),
        )
        self._project_invest_balance_cache[date] = {
            (str(row["c_projcode"]), str(row.get("c_pactid") or "")): to_decimal(row.get("acbalance"))
            for row in rows
        }
        return self._project_invest_balance_cache[date]

    def _project_invest_contract_starts_by_date(self, date: str) -> dict[tuple[str, str], str]:
        if date in self._project_invest_contract_start_cache:
            return self._project_invest_contract_start_cache[date]

        client, table = self._client_table("am_project_invest")
        project_code = self._field("am_project_invest", "project_code")
        close_date = self._field("am_project_invest", "close_date")
        pact_id = self._field("am_project_invest", "pact_id")
        contract_start = self._field("am_project_invest", "contract_start_date")
        rows = client.fetch_all(
            f"""
            SELECT
                {project_code} AS c_projcode,
                {close_date} AS d_cldate,
                {pact_id} AS c_pactid,
                MAX({contract_start}) AS d_bdate
            FROM {table}
            WHERE {close_date} = %s
            GROUP BY {project_code}, {close_date}, {pact_id}
            """,
            (date,),
        )
        self._project_invest_contract_start_cache[date] = {
            (str(row["c_projcode"]), str(row.get("c_pactid") or "")): str(row.get("d_bdate") or "")
            for row in rows
            if row.get("d_bdate") is not None
        }
        return self._project_invest_contract_start_cache[date]

    def _pact_assets_by_date(self, date: str) -> dict[tuple[str, str], list[PactAssetRow]]:
        if date in self._pact_asset_cache:
            return self._pact_asset_cache[date]

        client, table = self._client_table("am_pact_asset")
        invest_client, invest_table = self._client_table("am_project_invest")
        pact_project_code = self._field("am_pact_asset", "project_code")
        pact_close_date = self._field("am_pact_asset", "close_date")
        pact_asset_name = self._field("am_pact_asset", "asset_name")
        pact_stock_code = self._field("am_pact_asset", "stock_code")
        pact_pact_id = self._field("am_pact_asset", "pact_id")
        pact_spv_type = self._field("am_pact_asset", "spv_type")
        pact_asset_type = self._field("am_pact_asset", "asset_type")
        pact_data_source = self._field("am_pact_asset", "data_source")
        invest_project_code = self._field("am_project_invest", "project_code")
        invest_close_date = self._field("am_project_invest", "close_date")
        invest_pact_id = self._field("am_project_invest", "pact_id")
        invest_contract_start = self._field("am_project_invest", "contract_start_date")
        can_join_contract = client is invest_client
        rows = None
        for include_contract_start in (True, False):
            include_contract_start = include_contract_start and can_join_contract
            select_columns = [
                f"pact.{pact_project_code} AS c_projcode",
                f"pact.{pact_asset_name} AS c_udlyasset",
                f"pact.{pact_stock_code} AS c_stockcode",
                f"pact.{pact_pact_id} AS c_pactid",
                f"pact.{pact_spv_type} AS c_spv_type",
                f"pact.{pact_asset_type} AS c_assettype",
                f"pact.{pact_data_source} AS c_datasource",
                "invest.d_bdate" if include_contract_start else "NULL AS d_bdate",
            ]
            if include_contract_start:
                sql = f"""
                SELECT {", ".join(select_columns)}
                FROM {table} pact
                LEFT JOIN (
                    SELECT
                        {invest_project_code} AS c_projcode,
                        {invest_close_date} AS d_cldate,
                        {invest_pact_id} AS c_pactid,
                        MAX({invest_contract_start}) AS d_bdate
                    FROM {invest_table}
                    WHERE {invest_close_date} = %s
                    GROUP BY {invest_project_code}, {invest_close_date}, {invest_pact_id}
                ) invest
                    ON pact.{pact_project_code} = invest.c_projcode
                   AND pact.{pact_close_date} = invest.d_cldate
                   AND pact.{pact_pact_id} = invest.c_pactid
                WHERE pact.{pact_close_date} = %s
                """
                params = (date, date)
            else:
                sql = f"""
                SELECT {", ".join(select_columns)}
                FROM {table} pact
                WHERE pact.{pact_close_date} = %s
                """
                params = (date,)
            rows = client.fetch_all(sql, params)
            break
        if rows is None:
            rows = []
        contract_starts = {} if can_join_contract else self._project_invest_contract_starts_by_date(date)
        grouped_assets: dict[tuple[str, str], list[PactAssetRow]] = defaultdict(list)
        for row in rows:
            project_code_value = str(row["c_projcode"])
            pact_id_value = str(row.get("c_pactid") or "")
            contract_start_date = row.get("d_bdate")
            if contract_start_date is None and contract_starts:
                contract_start_date = contract_starts.get((project_code_value, pact_id_value))
            pact_asset = PactAssetRow(
                project_code=project_code_value,
                asset_name=str(row.get("c_udlyasset") or ""),
                stock_code=str(row.get("c_stockcode") or ""),
                pact_id=pact_id_value,
                spv_type=str(row.get("c_spv_type") or ""),
                asset_type=str(row.get("c_assettype") or ""),
                contract_start_date=str(contract_start_date) if contract_start_date else None,
                data_source=str(row.get("c_datasource") or ""),
            )
            grouped_assets[(pact_asset.project_code, pact_asset.asset_name)].append(pact_asset)
        self._pact_asset_cache[date] = dict(grouped_assets)
        return self._pact_asset_cache[date]


def _normalize_report_project_name_without_chinese_parentheses(value: str) -> str:
    name = re.sub(r"\uff08[^\uff08\uff09]*\uff09", "", value or "")
    name = unicodedata.normalize("NFKC", name).strip().lower()
    name = re.sub(r"\s+", "", name)
    name = re.sub(r"[_＿][^_＿]+$", "", name)
    return name
