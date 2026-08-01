from decimal import Decimal

import pytest

from auto_check.app.config import AppConfig, DataSourceConfig
from auto_check.app.repositories import AutoCheckRepository
from auto_check.app.reconcile_schema import ReconcileSchemaSettings, ReconcileSourceRef, ReconcileTableSchema


class FakeClient:
    def __init__(self):
        self.fetch_all_calls = []
        self.raise_missing_d_bdate = False
        self.asset_totals = {
            "P1": Decimal("100"),
            "P2": Decimal("200"),
        }
        self.fa4001 = {
            "P1": Decimal("10"),
            "P2": Decimal("20"),
        }
        self.valuation_rows = [
            {"c_projcode": "P1", "c_accountcode": "1001.01.01.01.0001", "c_accountname": "资产1", "f_marketvalue": Decimal("5")},
            {"c_projcode": "P1", "c_accountcode": "2001.01", "c_accountname": "费用1", "f_marketvalue": Decimal("6")},
            {"c_projcode": "P2", "c_accountcode": "1001.01.01.01.0002", "c_accountname": "资产2", "f_marketvalue": Decimal("7")},
            {"c_projcode": "P2", "c_accountcode": "2203.01", "c_accountname": "费用2", "f_marketvalue": Decimal("8")},
        ]
        self.pact_assets = [
            {"c_projcode": "P1", "c_udlyasset": "资产1", "c_stockcode": "0001", "c_pactid": "PACT1", "c_spv_type": "10", "c_assettype": "31", "c_datasource": "am"},
            {"c_projcode": "P2", "c_udlyasset": "资产2", "c_stockcode": "0002", "c_pactid": "PACT2", "c_spv_type": "11", "c_assettype": "32", "c_datasource": "ht"},
        ]
        self.project_invest_balances = [
            {"c_projcode": "P1", "d_cldate": "2026-04-30", "c_pactid": "PACT1", "acbalance": Decimal("123"), "d_bdate": "2025-01-01"},
            {"c_projcode": "P2", "d_cldate": "2026-04-30", "c_pactid": "PACT2", "acbalance": Decimal("0"), "d_bdate": "2024-01-01"},
        ]
        self.ta_dm_total = Decimal("300")
        self.ta_dws_total = Decimal("300")
        self.blank_client_type_rows = [
            {
                "tpm_pactid": "PACT1",
                "tpm_clientname": "客户A",
                "tpm_clientkind_tusp": "4",
                "tpm_clientkindex": "",
                "tpm_spvtype": "SPV",
                "tpm_htincome": Decimal("10"),
                "tpm_shareamt": Decimal("90"),
                "amount": Decimal("100"),
            }
        ]
        self.repo_amount_rows = [{"amount": Decimal("123")}]
        self.project_name_rows = [
            {"projname": "江苏信托稳盈集合资金信托计划（A类）"},
            {"projname": "其他项目"},
        ]
        self.security_balance_amount_rows = [
            {"stock_code": "ZQ001", "security_name": "23苏城投MTN001", "amount": Decimal("120")}
        ]

    def fetch_all(self, sql, params=()):
        self.fetch_all_calls.append((sql, tuple(params)))
        if self.raise_missing_d_bdate and "invest.d_bdate" in sql:
            raise RuntimeError("column invest.d_bdate does not exist")
        if "fa_accountbalance_dws" in sql:
            return self._fa4001_rows(sql, tuple(params))
        if "fa_valuationreport_dws" in sql and "c_accountcode = '0004'" in sql:
            return self._asset_total_rows(sql, tuple(params))
        if "fa_valuationreport_dws" in sql:
            return self._valuation_rows(sql, tuple(params))
        if "am_pactasset_dws" in sql:
            return self._pact_asset_rows(sql, tuple(params))
        if "am_projinvest_dws" in sql:
            return self._project_invest_rows(sql, tuple(params))
        if "ta_pact_survamt_day_zgxg_dm" in sql and "SUM" in sql:
            return [{"total": self.ta_dm_total}]
        if "ta_pact_detail_dws" in sql:
            return [{"total": self.ta_dws_total}]
        if "ta_pact_survamt_day_zgxg_dm" in sql:
            return self.blank_client_type_rows
        if "fa_security_balance_zgxg_dm" in sql and "GROUP BY sbm_stockcode, sbm_sename" in sql:
            return self.security_balance_amount_rows
        if "ex_pledge_back" in sql and "SUM" in sql:
            return self.repo_amount_rows
        if "zf_detail_2024" in sql:
            return self.project_name_rows
        return []

    def fetch_one(self, sql, params=()):
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def count_calls(self, table_name):
        return sum(1 for sql, _ in self.fetch_all_calls if table_name in sql)

    def _asset_total_rows(self, sql, params):
        if "c_projcode = %s" in sql:
            project_code = params[1]
            value = self.asset_totals.get(project_code)
            return [{"c_projcode": project_code, "f_marketvalue": value}] if value is not None else []
        return [
            {"c_projcode": project_code, "f_marketvalue": value}
            for project_code, value in self.asset_totals.items()
        ]

    def _fa4001_rows(self, sql, params):
        if "c_projcode = %s" in sql:
            project_code = params[1]
            return [{"c_projcode": project_code, "balance": self.fa4001.get(project_code, Decimal("0"))}]
        return [
            {"c_projcode": project_code, "balance": value}
            for project_code, value in self.fa4001.items()
        ]

    def _valuation_rows(self, sql, params):
        rows = self.valuation_rows
        if "c_projcode = %s" in sql:
            rows = [row for row in rows if row["c_projcode"] == params[1]]
        if "c_accountcode LIKE %s" in sql:
            prefix = params[-1].removesuffix("%")
            rows = [row for row in rows if row["c_accountcode"].startswith(prefix)]
        if "c_accountcode NOT LIKE %s" in sql:
            prefix = params[-1].removesuffix("%")
            rows = [row for row in rows if not row["c_accountcode"].startswith(prefix)]
        if "LENGTH(c_accountcode)" in sql:
            rows = [row for row in rows if row["c_accountcode"].count(".") == 4]
        return rows

    def _pact_asset_rows(self, sql, params):
        rows = self.pact_assets
        if "c_projcode = %s" in sql:
            project_code, _, asset_name = params
            rows = [
                row
                for row in rows
                if row["c_projcode"] == project_code and row["c_udlyasset"] == asset_name
            ]
        if "invest.d_bdate" in sql:
            contract_starts = {
                (str(row["c_projcode"]), str(row.get("c_pactid") or "")): row.get("d_bdate")
                for row in self.project_invest_balances
            }
            rows = [
                {
                    **row,
                    "d_bdate": contract_starts.get((str(row["c_projcode"]), str(row.get("c_pactid") or ""))),
                }
                for row in rows
            ]
        return rows

    def _project_invest_rows(self, sql, params):
        return self.project_invest_balances


def config():
    source = DataSourceConfig("postgresql", "localhost", 5432, "db", "dws", "u", "p")
    return AppConfig(dws=source, business=source)


def test_repository_uses_configured_table_and_field_names_for_valuation_totals():
    dws_client = FakeClient()
    schema = ReconcileSchemaSettings(
        version=1,
        tables={
            "fa_valuation": ReconcileTableSchema(
                source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
                table="custom.fa_valuation_custom",
                display_name="自定义估值表",
                fields={
                    "project_code": "proj_code",
                    "valuation_date": "val_date",
                    "account_code": "acct_code",
                    "account_name": "acct_name",
                    "market_value": "market_amt",
                },
            )
        },
    )
    repository = AutoCheckRepository(config(), schema=schema, dws_client=dws_client, business_client=FakeClient())

    repository.get_valuation_asset_total("P1", "2026-04-30")

    sql, params = dws_client.fetch_all_calls[-1]
    assert '"custom"."fa_valuation_custom"' in sql
    assert "proj_code AS c_projcode" in sql
    assert "market_amt AS f_marketvalue" in sql
    assert "val_date = %s" in sql
    assert "acct_code = '0004'" in sql
    assert params == ("2026-04-30",)


def test_repository_strict_schema_does_not_fill_missing_required_fields():
    schema = ReconcileSchemaSettings(
        version=1,
        strict=True,
        tables={
            "fa_valuation": ReconcileTableSchema(
                source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
                table="custom.fa_valuation_custom",
                fields={
                    "project_code": "proj_code",
                    "valuation_date": "val_date",
                    "market_value": "market_amt",
                },
            )
        },
    )
    repository = AutoCheckRepository(config(), schema=schema, dws_client=FakeClient(), business_client=FakeClient())

    with pytest.raises(ValueError, match=r"fa_valuation\.account_code"):
        repository.get_valuation_asset_total("P1", "2026-04-30")


def _am_required_schema(*, include_data_source=True, include_contract_start=True, invest_source_id="dws"):
    pact_fields = {
        "project_code": "c_projcode",
        "close_date": "d_cldate",
        "asset_name": "c_udlyasset",
        "stock_code": "c_stockcode",
        "pact_id": "c_pactid",
        "spv_type": "c_spv_type",
        "asset_type": "c_assettype",
    }
    if include_data_source:
        pact_fields["data_source"] = "c_datasource"
    invest_fields = {
        "project_code": "c_projcode",
        "close_date": "d_cldate",
        "pact_id": "c_pactid",
        "invest_balance": "f_acbalance",
    }
    if include_contract_start:
        invest_fields["contract_start_date"] = "d_bdate"
    return ReconcileSchemaSettings(
        version=1,
        strict=True,
        tables={
            "am_pact_asset": ReconcileTableSchema(
                source_ref=ReconcileSourceRef(id="dws", name="DWS", match_by="id_then_name"),
                table="am_pactasset_dws",
                fields=pact_fields,
            ),
            "am_project_invest": ReconcileTableSchema(
                source_ref=ReconcileSourceRef(id=invest_source_id, name=invest_source_id, match_by="id_then_name"),
                table="am_projinvest_dws",
                fields=invest_fields,
            ),
        },
    )


def test_repository_am_fields_that_drive_logic_are_required():
    missing_data_source = AutoCheckRepository(
        config(),
        schema=_am_required_schema(include_data_source=False),
        dws_client=FakeClient(),
        business_client=FakeClient(),
    )
    with pytest.raises(ValueError, match=r"am_pact_asset\.data_source"):
        missing_data_source.list_project_pact_assets("P1", "2026-04-30")

    missing_contract_start = AutoCheckRepository(
        config(),
        schema=_am_required_schema(include_contract_start=False),
        dws_client=FakeClient(),
        business_client=FakeClient(),
    )
    with pytest.raises(ValueError, match=r"am_project_invest\.contract_start_date"):
        missing_contract_start.list_project_pact_assets("P1", "2026-04-30")


def test_repository_reuses_date_level_dws_queries():
    dws_client = FakeClient()
    repository = AutoCheckRepository(config(), dws_client=dws_client, business_client=FakeClient())

    assert repository.get_valuation_asset_total("P1", "2026-04-30") == Decimal("100")
    assert repository.get_valuation_asset_total("P2", "2026-04-30") == Decimal("200")
    assert repository.get_fa_4001_balance("P1", "2026-04-30") == Decimal("10")
    assert repository.get_fa_4001_balance("P2", "2026-04-30") == Decimal("20")
    assert [row.account_code for row in repository.list_valuation_rows("P1", "2026-04-30", account_prefix="1")] == [
        "1001.01.01.01.0001"
    ]
    assert [row.account_code for row in repository.list_valuation_rows("P2", "2026-04-30", exclude_prefix="1", leaf_only=False)] == [
        "2203.01"
    ]
    assert repository.list_pact_assets("P1", "2026-04-30", "资产1")[0].stock_code == "0001"
    assert repository.list_pact_assets("P1", "2026-04-30", "资产1")[0].pact_id == "PACT1"
    assert repository.list_pact_assets("P1", "2026-04-30", "资产1")[0].spv_type == "10"
    assert repository.list_pact_assets("P1", "2026-04-30", "资产1")[0].asset_type == "31"
    assert repository.list_pact_assets("P1", "2026-04-30", "资产1")[0].data_source == "am"
    assert repository.list_pact_assets("P2", "2026-04-30", "资产2")[0].stock_code == "0002"
    assert [asset.stock_code for asset in repository.list_project_pact_assets("P1", "2026-04-30")] == ["0001"]
    assert repository.list_project_pact_assets("P1", "2026-04-30")[0].contract_start_date == "2025-01-01"
    assert repository.get_project_invest_balance("P1", "2026-04-30", "PACT1") == Decimal("123")
    assert repository.get_project_invest_balance("P2", "2026-04-30", "PACT2") == Decimal("0")

    assert dws_client.count_calls("fa_accountbalance_dws") == 1
    assert dws_client.count_calls("fa_valuationreport_dws") == 2
    assert dws_client.count_calls("am_pactasset_dws") == 1
    assert dws_client.count_calls("am_projinvest_dws") == 2


def test_repository_pact_assets_requires_contract_start_date_column():
    dws_client = FakeClient()
    dws_client.raise_missing_d_bdate = True
    repository = AutoCheckRepository(config(), dws_client=dws_client, business_client=FakeClient())

    with pytest.raises(RuntimeError, match="d_bdate"):
        repository.list_project_pact_assets("P1", "2026-04-30")

    pact_queries = [sql for sql, _ in dws_client.fetch_all_calls if "am_pactasset_dws" in sql]
    assert len(pact_queries) == 1
    assert "invest.d_bdate" in pact_queries[0]


def test_repository_pact_assets_fills_contract_start_date_across_sources_without_join():
    pact_client = FakeClient()
    invest_client = FakeClient()
    repository = AutoCheckRepository(
        config(),
        schema=_am_required_schema(invest_source_id="invest"),
        dws_client=pact_client,
        business_client=FakeClient(),
        source_clients={"invest": invest_client},
    )

    assets = repository.list_project_pact_assets("P1", "2026-04-30")

    assert [asset.stock_code for asset in assets] == ["0001"]
    assert assets[0].contract_start_date == "2025-01-01"
    pact_queries = [sql for sql, _ in pact_client.fetch_all_calls if "am_pactasset_dws" in sql]
    assert len(pact_queries) == 1
    assert "LEFT JOIN" not in pact_queries[0]
    assert invest_client.count_calls("am_projinvest_dws") == 1


def test_repository_pact_assets_cross_source_contract_start_fill_ignores_date_string_format():
    pact_client = FakeClient()
    invest_client = FakeClient()
    invest_client.project_invest_balances = [
        {
            "c_projcode": "P1",
            "d_cldate": "2026-04-30 00:00:00",
            "c_pactid": "PACT1",
            "acbalance": Decimal("123"),
            "d_bdate": "2025-01-01",
        }
    ]
    repository = AutoCheckRepository(
        config(),
        schema=_am_required_schema(invest_source_id="invest"),
        dws_client=pact_client,
        business_client=FakeClient(),
        source_clients={"invest": invest_client},
    )

    assets = repository.list_project_pact_assets("P1", "2026-04-30")

    assert assets[0].contract_start_date == "2025-01-01"


def test_repository_loads_ta_balance_totals_from_dm_and_dws_tables():
    dws_client = FakeClient()
    repository = AutoCheckRepository(config(), dws_client=dws_client, business_client=FakeClient())

    assert repository.get_ta_balance_totals("P1", "2026-04-30") == (Decimal("300"), Decimal("300"))

    ta_queries = [sql for sql, _ in dws_client.fetch_all_calls if "ta_pact" in sql]
    assert len(ta_queries) == 2
    assert '"dm"."ta_pact_survamt_day_zgxg_dm"' in ta_queries[0]
    assert '"dws"."ta_pact_detail_dws"' in ta_queries[1]
    assert dws_client.fetch_all_calls[-2][1] == ("2026-04-30", "P1")
    assert dws_client.fetch_all_calls[-1][1] == ("2026-04-30", "P1")


def test_repository_loads_security_balance_amounts_from_dm_table():
    dws_client = FakeClient()
    repository = AutoCheckRepository(config(), dws_client=dws_client, business_client=FakeClient())

    rows = repository.list_security_balance_amounts("P1", "2026-04-30")

    assert rows == [{"stock_code": "ZQ001", "security_name": "23苏城投MTN001", "amount": Decimal("120")}]
    sql, params = dws_client.fetch_all_calls[-1]
    assert '"dm"."fa_security_balance_zgxg_dm"' in sql
    assert "GROUP BY sbm_stockcode, sbm_sename" in sql
    assert "COALESCE(sbm_balamoney_cost, 0)" in sql
    assert "TRIM(COALESCE(sbm_seclas_h2024, '')) <> ''" in sql
    assert params == ("P1", "2026-04-30")


def test_repository_loads_blank_ta_client_type_rows_with_dependent_conditions():
    dws_client = FakeClient()
    repository = AutoCheckRepository(config(), dws_client=dws_client, business_client=FakeClient())

    rows = repository.list_blank_ta_client_type_rows("P1", "2026-04-30")

    assert rows == [
        {
            "pact_id": "PACT1",
            "client_name": "客户A",
            "client_kind": "4",
            "client_kind_index": "",
            "spv_type": "SPV",
            "ht_income": Decimal("10"),
            "share_amount": Decimal("90"),
            "amount": Decimal("100"),
        }
    ]
    sql, params = dws_client.fetch_all_calls[-1]
    assert '"dm"."ta_pact_survamt_day_zgxg_dm"' in sql
    assert "tpm_clientkind_tusp IS NULL" in sql
    assert "tpm_clientkind_tusp = '4'" in sql
    assert "tpm_clientkindex IS NULL" in sql
    assert "tpm_clientkind_tusp = '5'" in sql
    assert "tpm_spvtype IS NULL" in sql
    assert params == ("2026-04-30", "P1")


def test_repository_asset_missing_refinement_queries_use_confirmed_filters():
    dws_client = FakeClient()
    business_client = FakeClient()
    repository = AutoCheckRepository(config(), dws_client=dws_client, business_client=business_client)

    repository.get_security_balance_refinement("P1", "2026-04-30", "102381204", "23苏城投MTN004")
    security_sql, security_params = dws_client.fetch_all_calls[-1]
    assert '"dm"."fa_security_balance_zgxg_dm"' in security_sql
    assert "sbm_projcode = %s" in security_sql
    assert "sbm_cacldate = %s" in security_sql
    assert "sbm_stockcode = %s" in security_sql
    assert "sbm_sename = %s" in security_sql
    assert "COALESCE(sbm_balamoney_cost, 0)" in security_sql
    assert security_params == ("P1", "2026-04-30", "102381204", "23苏城投MTN004")

    repository.get_dm_project_invest_refinement("P1", "2026-04-30", "DK1")
    invest_sql, invest_params = dws_client.fetch_all_calls[-1]
    assert '"dm"."am_projinvest_zgxg_dm"' in invest_sql
    assert "pin_projcode = %s" in invest_sql
    assert "pin_cldate = %s" in invest_sql
    assert "pin_mpactid = %s" in invest_sql
    assert "COALESCE(pin_acbalance, 0) <> 0" in invest_sql
    assert invest_params == ("P1", "2026-04-30", "DK1")

    repository.get_spv_project_invest_refinement("P1", "2026-04-30", "PACT1")
    spv_sql, spv_params = dws_client.fetch_all_calls[-1]
    assert '"dm"."am_projinvest_spv_zgxg_dm"' in spv_sql
    assert "svd_projcode = %s" in spv_sql
    assert "svd_cldate = %s" in spv_sql
    assert "svd_mpactid = %s" in spv_sql
    assert "COALESCE(svd_balamoney_cost, 0)" in spv_sql
    assert spv_params == ("P1", "2026-04-30", "PACT1")

    repository.get_property_right_refinement("P1", "CC1")
    property_sql, property_params = dws_client.fetch_all_calls[-1]
    assert '"zgxg_zhbs"."ccqxx"' in property_sql
    assert "pjdw_projcode = %s" in property_sql
    assert "pin_mpactid = %s" in property_sql
    assert "pin_cldate" not in property_sql
    assert "COALESCE(pin_acbalance, 0) <> 0" in property_sql
    assert property_params == ("P1", "CC1")

    assert repository.has_report_rows(("currency_report_24", "currency_detail_project_2_1_9"), "2026-04-30") is False
    report_sql, report_params = business_client.fetch_all_calls[-1]
    assert '"currency_report_24"."currency_detail_project_2_1_9"' in report_sql
    assert "caldate = %s" in report_sql
    assert report_params == ("2026-04-30",)

    assert repository.count_report_project_name_matches_without_chinese_parentheses(
        "2026-04-30",
        "江苏信托稳盈集合资金信托计划",
    ) == 1
    project_name_sql, project_name_params = business_client.fetch_all_calls[-1]
    assert "zf_detail_2024" in project_name_sql
    assert "projname" in project_name_sql
    assert "caldate = %s" in project_name_sql
    assert project_name_params == ("2026-04-30",)

    repository.has_reverse_repo_blank_rows("P1")
    repo_sql, repo_params = business_client.fetch_all_calls[-1]
    assert '"ass_man_reg"."ex_pledge_back"' in repo_sql
    assert "project_code = %s" in repo_sql
    assert "subcode LIKE %s" in repo_sql
    assert "buyback_money IS NULL" in repo_sql
    assert "expenses IS NULL" in repo_sql
    assert repo_params == ("P1", "7%")


def test_repository_loads_reverse_and_positive_repo_business_amounts_with_confirmed_filters():
    business_client = FakeClient()
    repository = AutoCheckRepository(config(), dws_client=FakeClient(), business_client=business_client)

    assert repository.get_reverse_repo_business_amount("P1") == Decimal("123")
    reverse_sql, reverse_params = business_client.fetch_all_calls[-1]
    assert '"ass_man_reg"."ex_pledge_back"' in reverse_sql
    assert "project_code = %s" in reverse_sql
    assert "subcode LIKE %s" in reverse_sql
    assert "COALESCE(buyback_money, 0) + COALESCE(expenses, 0)" in reverse_sql
    assert reverse_params == ("P1", "7%")

    assert repository.get_positive_repo_business_amount("P1") == Decimal("123")
    positive_sql, positive_params = business_client.fetch_all_calls[-1]
    assert '"ass_man_reg"."ex_pledge_back"' in positive_sql
    assert "project_code = %s" in positive_sql
    assert "subcode LIKE %s" in positive_sql
    assert "COALESCE(buyback_money, 0) - COALESCE(expenses, 0)" in positive_sql
    assert positive_params == ("P1", "8%")
