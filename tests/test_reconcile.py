from decimal import Decimal

from auto_check.engine.models import PactAssetRow, ProjectBalance, ValuationRow
from auto_check.engine.reconcile import NoSourceReportData, ReconcileEngine


class FakeRepo:
    def __init__(self):
        self.projects = []
        self.fa4001 = {}
        self.ta = {}
        self.asset_total = {}
        self.valuation = {}
        self.pact_assets = {}
        self.project_invest_balances = {}
        self.ta_dm_total = {}
        self.ta_dws_total = {}
        self.ta_blank_client_type_rows = {}
        self.security_refinements = {}
        self.security_balance_amounts = {}
        self.dm_project_invest_refinements = {}
        self.spv_project_invest_refinements = {}
        self.property_right_refinements = {}
        self.report_rows = set()
        self.reverse_repo_blank_projects = set()
        self.reverse_repo_business_amounts = {}
        self.positive_repo_business_amounts = {}
        self.valuation_calls = []
        self.valuation_row_calls = []

    def list_project_balances(self, date):
        return self.projects

    def get_fa_4001_balance(self, project_code, date):
        return self.fa4001.get(project_code, Decimal("0"))

    def get_ta_assetshare_sum(self, project_code, date):
        return self.ta.get(project_code, Decimal("0"))

    def get_valuation_asset_total(self, project_code, date):
        return self.asset_total.get(project_code)

    def list_valuation_leaf_rows(self, project_code, date, account_prefix=None):
        self.valuation_calls.append((project_code, account_prefix))
        rows = self.valuation.get(project_code, [])
        if account_prefix:
            return [row for row in rows if row.account_code.startswith(account_prefix)]
        return rows

    def list_valuation_rows(self, project_code, date, account_prefix=None, exclude_prefix=None, leaf_only=True):
        self.valuation_row_calls.append((project_code, account_prefix, exclude_prefix, leaf_only))
        rows = self.valuation.get(project_code, [])
        if account_prefix:
            rows = [row for row in rows if row.account_code.startswith(account_prefix)]
        if exclude_prefix:
            rows = [row for row in rows if not row.account_code.startswith(exclude_prefix)]
        if leaf_only:
            rows = [row for row in rows if row.account_code.count(".") == 4]
        return rows

    def list_pact_assets(self, project_code, date, asset_name):
        return self.pact_assets.get((project_code, asset_name), [])

    def list_project_pact_assets(self, project_code, date):
        rows = []
        for (asset_project_code, _), pact_assets in self.pact_assets.items():
            if asset_project_code == project_code:
                rows.extend(pact_assets)
        return rows

    def get_project_invest_balance(self, project_code, date, pact_id):
        return self.project_invest_balances.get((project_code, pact_id))

    def get_ta_balance_totals(self, project_code, date):
        return (
            self.ta_dm_total.get(project_code, Decimal("0")),
            self.ta_dws_total.get(project_code, Decimal("0")),
        )

    def list_blank_ta_client_type_rows(self, project_code, date):
        return self.ta_blank_client_type_rows.get(project_code, [])

    def get_security_balance_refinement(self, project_code, date, stock_code, security_name):
        return self.security_refinements.get((project_code, stock_code, security_name))

    def list_security_balance_amounts(self, project_code, date):
        return self.security_balance_amounts.get(project_code, [])

    def get_dm_project_invest_refinement(self, project_code, date, pact_id):
        return self.dm_project_invest_refinements.get((project_code, pact_id))

    def get_dm_project_invest_contract_balance(self, project_code, date, pact_id):
        return self.dm_project_invest_refinements.get((project_code, pact_id))

    def get_spv_project_invest_refinement(self, project_code, date, pact_id):
        return self.spv_project_invest_refinements.get((project_code, pact_id))

    def get_property_right_refinement(self, project_code, pact_id):
        return self.property_right_refinements.get((project_code, pact_id))

    def has_report_rows(self, table_parts, date):
        return (tuple(table_parts), date) in self.report_rows

    def has_reverse_repo_blank_rows(self, project_code):
        return project_code in self.reverse_repo_blank_projects

    def get_reverse_repo_business_amount(self, project_code):
        return self.reverse_repo_business_amounts.get(project_code, Decimal("0"))

    def get_positive_repo_business_amount(self, project_code):
        return self.positive_repo_business_amounts.get(project_code, Decimal("0"))


def test_no_source_report_data_raises_clear_state():
    repo = FakeRepo()

    try:
        ReconcileEngine(repo).run("2026-04-30")
    except NoSourceReportData as exc:
        assert exc.date == "2026-04-30"
        assert "报表对应日期无数据" in str(exc)
    else:
        raise AssertionError("NoSourceReportData was not raised")


def test_zero_difference_report_rows_return_empty_results():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P0", "Balanced Project", Decimal("100"), Decimal("100"), Decimal("20"))]

    assert ReconcileEngine(repo).run("2026-04-30") == []


def test_received_trust_is_not_checked_until_asset_total_matches_valuation_asset():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"), Decimal("20"))]
    repo.fa4001["P1"] = Decimal("10")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("1001.01.01.01.0002", "Asset A", Decimal("100"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].match_status == "已解释"
    assert repo.valuation_row_calls == [("P1", None, None, False)]


def test_asset_missing_matches_prefix_1_leaf_rows_by_asset_gap():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("2001.01.01.01.0001", "ignored", Decimal("100")),
        ValuationRow("1001.01.01.01.0002", "Asset A", Decimal("100")),
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert repo.valuation_row_calls == [("P1", None, None, False)]
    assert results[0].difference_reason == "资产缺失"
    assert results[0].valuation_match.rows[0].account_code.startswith("1")
    assert results[0].details[0].kind == "asset_gap"
    assert results[0].details[0].data["asset_gap"] == "100"


def test_asset_missing_matches_positive_3001_common_receivable_as_asset_candidate():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("3001.01", "应收账款共同类", Decimal("100")),
        ValuationRow("4002", "其他收益", Decimal("100")),
    ]

    results = ReconcileEngine(repo).run("2026-06-12")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.rows[0].account_code == "3001.01"
    assert results[0].details[0].data["specific_reason"] == "应收账款_共同类资产缺失"
    assert results[0].details[-1].data["specific_reason"] == "①应收账款_共同类缺失：应收账款共同类"


def test_asset_difference_when_asset_gap_does_not_match_specific_asset_rows():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("1001.01.01.01.0002", "Asset A", Decimal("30"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "未解释"
    assert results[0].details[0].data["reason"] == "资产缺失"


def test_result_keeps_valuation_asset_total_for_list_display():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("1001.01.01.01.0002", "Asset A", Decimal("100"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].valuation_asset_total == Decimal("1000")


def test_asset_missing_uses_actual_leaf_accounts_without_four_dot_limit():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("10000000"), Decimal("20000000"))]
    repo.asset_total["P1"] = Decimal("20000000")
    repo.valuation["P1"] = [
        ValuationRow("1541.01", "太平乐享二年年金保险", Decimal("10000000")),
        ValuationRow("1541.01.CC8250MX", "太平乐享二年年金保险（分红型）", Decimal("5000000")),
        ValuationRow("1541.01.CC8250MY", "太平鸿鑫金生2.0终身寿险（分红型）", Decimal("5000000")),
    ]

    results = ReconcileEngine(repo).run("2026-05-31")

    assert repo.valuation_row_calls == [("P1", None, None, False)]
    assert results[0].difference_reason == "资产缺失"
    assert results[0].match_status == "已解释"
    assert [row.account_code for row in results[0].valuation_match.rows] == [
        "1541.01.CC8250MX",
        "1541.01.CC8250MY",
    ]


def test_asset_missing_multiple_candidate_combinations_is_candidate_ambiguous():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("800"))]
    repo.asset_total["P1"] = Decimal("950")
    repo.valuation["P1"] = [
        ValuationRow("1001.01.01.01.0001", "资产A", Decimal("20")),
        ValuationRow("1002.01.01.01.0002", "资产B", Decimal("30")),
        ValuationRow("1003.01.01.01.0003", "资产C", Decimal("10")),
        ValuationRow("1004.01.01.01.0004", "资产D", Decimal("40")),
    ]

    results = ReconcileEngine(repo).run("2026-06-03")

    assert results[0].difference == Decimal("100")
    assert results[0].details[0].data["asset_gap"] == "50"
    assert results[0].difference_reason == "资产缺失 + 暂无法确定"
    assert results[0].match_status == "候选不唯一"
    assert results[0].valuation_match.match_type == "ambiguous_combination"
    assert results[0].details[0].data["specific_reason"] == "候选不唯一"
    assert [
        [row["account_name"] for row in group["rows"]]
        for group in results[0].details[0].data["candidate_groups"]
    ] == [
        ["资产A", "资产B"],
        ["资产C", "资产D"],
    ]


def test_asset_missing_ambiguous_candidates_can_be_confirmed_by_am_refinement():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("800"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1101.05.03.01.0001", "信托计划A_估值后缀", Decimal("60")),
        ValuationRow("1101.05.03.01.0002", "信托计划B", Decimal("40")),
        ValuationRow("1101.02.01.01.ZQ001", "债券C", Decimal("70")),
        ValuationRow("1101.02.01.01.ZQ002", "债券D", Decimal("30")),
    ]
    repo.pact_assets[("P1", "信托计划A")] = [PactAssetRow("P1", "信托计划A", "9999", "PACT_A")]
    repo.pact_assets[("P1", "信托计划B")] = [PactAssetRow("P1", "信托计划B", "0002", "PACT_B")]
    repo.project_invest_balances[("P1", "PACT_B")] = Decimal("0")

    results = ReconcileEngine(repo).run("2026-06-03")

    assert results[0].difference == Decimal("100")
    assert results[0].difference_reason == "资产缺失"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.match_type == "combination"
    assert results[0].valuation_match.message == "候选不唯一，经AM复核确认：候选组合2"
    assert [row.account_name for row in results[0].valuation_match.rows] == ["信托计划A_估值后缀", "信托计划B"]
    assert [detail.kind for detail in results[0].details] == [
        "asset_gap",
        "fa_am",
        "project_invest_balance",
        "asset_missing_refinement",
    ]
    assert results[0].details[0].data["match_type"] == "combination"
    assert results[0].details[0].data["specific_reason"] == "特定目的载体资产缺失"
    assert len(results[0].details[0].data["candidate_groups"]) == 2
    assert results[0].details[1].data["specific_reason"] == "FA与AM标的不一致"
    assert results[0].details[2].data["specific_reason"] == "合同投融资余额为0但FA科目余额不为0"
    assert results[0].details[-1].data["specific_reason"] == "\n".join(
        [
            "①特定目的载体缺失：信托计划A_估值后缀；原因：FA和AM标的不一致",
            "②特定目的载体缺失：信托计划B；原因：合同投融资余额为0但FA科目余额不为0",
        ]
    )


def test_asset_missing_am_confirmation_checks_candidates_beyond_display_limit():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("800"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1101.02.01.01.ZQ001", "债券一", Decimal("1")),
        ValuationRow("1101.02.01.01.ZQ002", "债券二", Decimal("99")),
        ValuationRow("1101.02.01.01.ZQ003", "债券三", Decimal("2")),
        ValuationRow("1101.02.01.01.ZQ004", "债券四", Decimal("98")),
        ValuationRow("1101.02.01.01.ZQ005", "债券五", Decimal("3")),
        ValuationRow("1101.02.01.01.ZQ006", "债券六", Decimal("97")),
        ValuationRow("1101.02.01.01.ZQ007", "债券七", Decimal("4")),
        ValuationRow("1101.02.01.01.ZQ008", "债券八", Decimal("96")),
        ValuationRow("1101.02.01.01.ZQ009", "债券九", Decimal("5")),
        ValuationRow("1101.02.01.01.ZQ010", "债券十", Decimal("95")),
        ValuationRow("1101.05.03.01.0001", "信托计划A_估值后缀", Decimal("60")),
        ValuationRow("1101.05.03.01.0002", "信托计划B", Decimal("40")),
    ]
    repo.pact_assets[("P1", "信托计划A")] = [PactAssetRow("P1", "信托计划A", "9999", "PACT_A")]
    repo.pact_assets[("P1", "信托计划B")] = [PactAssetRow("P1", "信托计划B", "0002", "PACT_B")]
    repo.project_invest_balances[("P1", "PACT_B")] = Decimal("0")

    results = ReconcileEngine(repo).run("2026-06-03")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].match_status == "已解释"
    assert [row.account_name for row in results[0].valuation_match.rows] == ["信托计划A_估值后缀", "信托计划B"]
    assert len(results[0].details[0].data["candidate_groups"]) == 5
    assert all(
        row["account_name"].startswith("债券")
        for group in results[0].details[0].data["candidate_groups"]
        for row in group["rows"]
    )


def test_asset_missing_specific_reason_lists_matched_asset_types():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("950"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1501.01.01.01.102381204", "23苏城投MTN004", Decimal("10")),
        ValuationRow("1101.01.01.01.600000", "浦发银行", Decimal("10")),
        ValuationRow("1101.04.01.01.000001", "华夏成长基金", Decimal("10")),
        ValuationRow("1111.12.34.01.RGC001", "质押式逆回购", Decimal("10")),
        ValuationRow("1501.04.05.01.DK20260531001", "流动资金贷款", Decimal("10")),
    ]
    repo.security_refinements[("P1", "102381204", "23苏城投MTN004")] = {"sbm_seclas_h2024": "01"}
    repo.security_refinements[("P1", "600000", "浦发银行")] = {"sbm_gpgqtype_h": "01"}
    repo.security_refinements[("P1", "000001", "华夏成长基金")] = {"sbm_fundtype": "1"}
    repo.dm_project_invest_refinements[("P1", "DK20260531001")] = {"pin_acbalance": Decimal("10")}
    repo.report_rows.add((("currency_report_24", "currency_detail_project_2_1_4"), "2026-05-31"))
    repo.report_rows.add((("currency_report_24", "currency_detail_project_2_1_5"), "2026-05-31"))
    repo.report_rows.add((("currency_report_24", "currency_detail_project_2_1_6"), "2026-05-31"))
    repo.report_rows.add((("currency_report_24", "currency_detail_project_2_1_2"), "2026-05-31"))

    results = ReconcileEngine(repo).run("2026-05-31")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].details[-1].data["specific_reason"] == "\n".join(
        [
            "①债券缺失：23苏城投MTN004",
            "②股票缺失：浦发银行",
            "③公募基金缺失：华夏成长基金",
            "④逆回购缺失：质押式逆回购",
            "⑤贷款缺失：流动资金贷款",
        ]
    )


def test_asset_missing_bond_refinement_sets_numbered_specific_reason():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("1101.02.15.01.102381204", "23苏城投MTN004", Decimal("100"))]
    repo.security_refinements[("P1", "102381204", "23苏城投MTN004")] = {"sbm_seclas_h2024": ""}

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].details[-1].kind == "asset_missing_refinement"
    assert results[0].details[-1].data["specific_reason"] == (
        "①债券缺失：23苏城投MTN004；原因：该债券债券类别_人行字段（sbm_seclas_h2024）为空"
    )
    assert results[0].details[-1].data["rows"][0]["asset_type"] == "债券"
    assert results[0].details[-1].data["rows"][0]["reason"] == "该债券债券类别_人行字段（sbm_seclas_h2024）为空"


def test_asset_missing_multiple_refinements_are_numbered_in_specific_reason():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("800"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1501.01.01.01.102381204", "23苏城投MTN004", Decimal("100")),
        ValuationRow("1303.01.01.DK20260531001", "贷款合同DK20260531001", Decimal("100")),
    ]
    repo.security_refinements[("P1", "102381204", "23苏城投MTN004")] = {"sbm_seclas_h2024": "01"}

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].details[-1].data["specific_reason"] == "\n".join(
        [
            "①债券缺失：23苏城投MTN004；原因：资负数据子系统-债务证券明细表无数据",
            "②贷款缺失：贷款合同DK20260531001；原因：该贷款在dm.am_projinvest_zgxg_dm不存在或投融资余额为0",
        ]
    )


def test_asset_missing_spv_keeps_project_invest_zero_reason_in_new_format():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("1101.05.03.01.0002", "江苏信托鑫享信托计划", Decimal("100"))]
    repo.pact_assets[("P1", "江苏信托鑫享信托计划")] = [
        PactAssetRow("P1", "江苏信托鑫享信托计划", "0002", "PACT1")
    ]
    repo.project_invest_balances[("P1", "PACT1")] = Decimal("0")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].details[-1].kind == "asset_missing_refinement"
    assert results[0].details[-1].data["specific_reason"] == (
        "①特定目的载体缺失：江苏信托鑫享信托计划；原因：合同投融资余额为0但FA科目余额不为0"
    )


def test_asset_missing_spv_income_certificate_checks_other_debt_report_after_spv_balance():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("1101.05.03.01.0002", "江苏信托收益凭证一号", Decimal("100"))]
    repo.pact_assets[("P1", "江苏信托收益凭证一号")] = [
        PactAssetRow("P1", "江苏信托收益凭证一号", "0002", "PACT1")
    ]
    repo.project_invest_balances[("P1", "PACT1")] = Decimal("100")
    repo.spv_project_invest_refinements[("P1", "PACT1")] = {"svd_assettype": ""}

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].details[-1].data["specific_reason"] == (
        "①特定目的载体缺失：江苏信托收益凭证一号；原因：该收益凭证在资负数据子系统-其他债权明细表无数据"
    )


def test_asset_missing_refinement_covers_additional_asset_types():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("930"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1101.01.01.01.600000", "浦发银行", Decimal("10")),
        ValuationRow("1101.04.01.01.000001", "华夏成长基金", Decimal("10")),
        ValuationRow("1101.05.06.01.SM001", "某私募基金", Decimal("10")),
        ValuationRow("1111.12.34.01.RGC001", "质押式逆回购", Decimal("10")),
        ValuationRow("1511.01.01.GQ20260531001", "股权投资GQ20260531001", Decimal("10")),
        ValuationRow("1541.01.CCPLAN001", "江苏信托稳赢信托产品一号", Decimal("10")),
        ValuationRow("1541.01.CCASSET001", "某资产收益权", Decimal("10")),
    ]
    repo.security_refinements[("P1", "600000", "浦发银行")] = {"sbm_gpgqtype_h": ""}
    repo.security_refinements[("P1", "000001", "华夏成长基金")] = {"sbm_fundtype": ""}
    repo.security_refinements[("P1", "SM001", "某私募基金")] = {"sbm_fundtype": "2"}
    repo.reverse_repo_blank_projects.add("P1")
    repo.dm_project_invest_refinements[("P1", "GQ20260531001")] = {"pin_acbalance": Decimal("10"), "pin_gqtype_h": ""}
    repo.spv_project_invest_refinements[("P1", "CCPLAN001")] = {"svd_assettype": "31"}

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].details[-1].data["specific_reason"] == "\n".join(
        [
            "①股票缺失：浦发银行；原因：该股票股票股权类别_人行字段（sbm_gpgqtype_h）为空",
            "②公募基金缺失：华夏成长基金；原因：该公募基金公募私募_人行字段（sbm_fundtype）为空",
            "③私募基金缺失：某私募基金；原因：资负数据子系统-特定目的载体明细表无数据",
            "④逆回购缺失：质押式逆回购；原因：存续回购业务表回购金额或佣金存在空数据",
            "⑤股权投资缺失：股权投资GQ20260531001；原因：该股权投资股权投资类别字段（pin_gqtype_h）为空",
            "⑥信托计划收益权缺失：江苏信托稳赢信托产品一号；原因：资负数据子系统-特定目的载体明细表无数据",
            "⑦资产收益权缺失：某资产收益权；原因：该财产权在zgxg_zhbs.ccqxx不存在或投融资余额为0",
        ]
    )


def test_asset_duplicate_matches_prefix_1_leaf_rows_by_asset_gap():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1100"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1001.01.01.01.0002", "Asset A", Decimal("100")),
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert repo.valuation_row_calls == [("P1", None, None, False)]
    assert results[0].difference_reason == "资产重复"
    assert results[0].details[0].data["asset_gap"] == "100"


def test_asset_duplicate_multiple_candidate_combinations_is_candidate_ambiguous():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1100"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1050")
    repo.valuation["P1"] = [
        ValuationRow("1001.01.01.01.0001", "资产A", Decimal("20")),
        ValuationRow("1002.01.01.01.0002", "资产B", Decimal("30")),
        ValuationRow("1003.01.01.01.0003", "资产C", Decimal("10")),
        ValuationRow("1004.01.01.01.0004", "资产D", Decimal("40")),
    ]

    results = ReconcileEngine(repo).run("2026-06-03")

    assert results[0].difference == Decimal("100")
    assert results[0].details[0].data["asset_gap"] == "50"
    assert results[0].difference_reason == "资产重复 + 暂无法确定"
    assert results[0].match_status == "候选不唯一"
    assert results[0].valuation_match.match_type == "ambiguous_combination"
    assert results[0].details[0].data["specific_reason"] == "候选不唯一"
    assert [
        [row["account_name"] for row in group["rows"]]
        for group in results[0].details[0].data["candidate_groups"]
    ] == [
        ["资产A", "资产B"],
        ["资产C", "资产D"],
    ]


def test_asset_duplicate_specific_reason_lists_matched_asset_types():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1100"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1501.01.01.01.102381204", "23苏城投MTN004", Decimal("60")),
        ValuationRow("1303.01.01.DK20260531001", "流动资金贷款", Decimal("20")),
        ValuationRow("1501.04.05.01.DK20260531002", "信托贷款", Decimal("20")),
    ]

    results = ReconcileEngine(repo).run("2026-05-31")

    assert results[0].difference_reason == "资产重复"
    assert results[0].details[0].data["specific_reason"] == "债券、贷款资产重复"


def test_asset_duplicate_refinement_flags_private_fund_when_am_is_not_private_spv():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1250"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1101.05.06.01.SM001", "某私募产品一号", Decimal("100")),
        ValuationRow("1101.05.06.01.SM002", "某私募产品二号", Decimal("100")),
        ValuationRow("1501.01.01.01.102381204", "23苏城投MTN004", Decimal("50")),
    ]
    repo.pact_assets[("P1", "某私募产品一号")] = [
        PactAssetRow("P1", "某私募产品一号", "SM001", "PACT1", "10", "31")
    ]
    repo.pact_assets[("P1", "某私募产品二号")] = [
        PactAssetRow("P1", "某私募产品二号", "SM002", "PACT2", "11", "31")
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产重复"
    assert [detail.kind for detail in results[0].details] == ["asset_gap", "asset_duplicate_refinement"]
    assert results[0].details[-1].data["specific_reason"] == "\n".join(
        [
            "①私募基金重复：某私募产品一号；原因：该资产在证券信息表中为私募产品但在AM中不为私募产品",
            "②私募基金重复：某私募产品二号",
            "③债券重复：1501.01.01.01.102381204 23苏城投MTN004",
        ]
    )
    assert results[0].details[-1].data["rows"][0]["am_spv_type"] == "10"
    assert results[0].details[-1].data["rows"][0]["am_asset_type"] == "31"
    assert results[0].details[-1].data["rows"][0]["reason"] == "该资产在证券信息表中为私募产品但在AM中不为私募产品"
    assert results[0].details[-1].data["rows"][1]["reason"] == ""
    assert results[0].details[-1].data["rows"][2]["asset_name"] == "1501.01.01.01.102381204 23苏城投MTN004"


def test_asset_duplicate_uses_actual_leaf_accounts_without_four_dot_limit():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("20000000"), Decimal("10000000"))]
    repo.asset_total["P1"] = Decimal("10000000")
    repo.valuation["P1"] = [
        ValuationRow("1541.01", "太平乐享二年年金保险", Decimal("10000000")),
        ValuationRow("1541.01.CC8250MX", "太平乐享二年年金保险（分红型）", Decimal("5000000")),
        ValuationRow("1541.01.CC8250MY", "太平鸿鑫金生2.0终身寿险（分红型）", Decimal("5000000")),
    ]

    results = ReconcileEngine(repo).run("2026-05-31")

    assert repo.valuation_row_calls == [("P1", None, None, False)]
    assert results[0].difference_reason == "资产重复"
    assert results[0].match_status == "已解释"
    assert [row.account_code for row in results[0].valuation_match.rows] == [
        "1541.01.CC8250MX",
        "1541.01.CC8250MY",
    ]


def test_asset_duplicate_uses_1541_contract_invest_difference_when_am_exceeds_valuation():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("20000000"), Decimal("10000000"))]
    repo.asset_total["P1"] = Decimal("10000000")
    repo.valuation["P1"] = [
        ValuationRow("1541.01", "财产权投资", Decimal("10000000")),
        ValuationRow("1541.01.PACTA", "财产权A", Decimal("5000000")),
        ValuationRow("1541.01.PACTB", "财产权B", Decimal("5000000")),
    ]
    repo.project_invest_balances[("P1", "PACTA")] = Decimal("10000000")
    repo.project_invest_balances[("P1", "PACTB")] = Decimal("10000000")

    results = ReconcileEngine(repo).run("2026-05-31")

    assert results[0].difference_reason == "资产重复"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.rows == [
        ValuationRow("1541.01.PACTA", "财产权A", Decimal("5000000")),
        ValuationRow("1541.01.PACTB", "财产权B", Decimal("5000000")),
    ]
    assert results[0].details[-1].kind == "asset_duplicate_refinement"


def test_asset_missing_uses_1541_contract_invest_difference_when_am_less_than_valuation():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("10000000"), Decimal("20000000"))]
    repo.asset_total["P1"] = Decimal("20000000")
    repo.valuation["P1"] = [
        ValuationRow("1541.01", "财产权投资", Decimal("10000000")),
        ValuationRow("1541.01.PACTA", "财产权A", Decimal("5000000")),
        ValuationRow("1541.01.PACTB", "财产权B", Decimal("5000000")),
    ]
    repo.project_invest_balances[("P1", "PACTA")] = Decimal("0")
    repo.project_invest_balances[("P1", "PACTB")] = Decimal("0")

    results = ReconcileEngine(repo).run("2026-05-31")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.rows == [
        ValuationRow("1541.01.PACTA", "财产权A", Decimal("5000000")),
        ValuationRow("1541.01.PACTB", "财产权B", Decimal("5000000")),
    ]
    assert results[0].details[-1].kind == "asset_missing_refinement"


def test_asset_gap_uses_fourth_level_group_combination_after_full_leaf_overflow():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("930"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1001.01.01.01.A", "同类资产A", Decimal("30")),
        ValuationRow("1001.01.01.01.B", "同类资产B", Decimal("40")),
        ValuationRow("1001.02.01.01.C", "其他资产C", Decimal("10")),
        ValuationRow("1001.02.01.01.D", "其他资产D", Decimal("20")),
    ]

    results = ReconcileEngine(repo, max_combination_rows=3).run("2026-06-01")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.match_type == "combination"
    assert results[0].valuation_match.message == "分类组合命中：1001.01.01.01"
    assert [row.account_code for row in results[0].valuation_match.rows] == [
        "1001.01.01.01.A",
        "1001.01.01.01.B",
    ]
    assert results[0].details[0].data["match_message"] == "分类组合命中：1001.01.01.01"


def test_asset_gap_natural_group_multiple_combinations_is_candidate_ambiguous():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("930"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1001.01.01.01.A", "同类资产A", Decimal("30")),
        ValuationRow("1001.01.01.01.B", "同类资产B", Decimal("40")),
        ValuationRow("1001.02.01.01.C", "其他资产C", Decimal("20")),
        ValuationRow("1001.02.01.01.D", "其他资产D", Decimal("50")),
    ]

    results = ReconcileEngine(repo, max_combination_rows=3).run("2026-06-01")

    assert results[0].difference_reason == "资产缺失 + 暂无法确定"
    assert results[0].match_status == "候选不唯一"
    assert results[0].valuation_match.match_type == "ambiguous_combination"
    assert results[0].details[0].data["specific_reason"] == "候选不唯一"
    assert [
        [row["account_name"] for row in group["rows"]]
        for group in results[0].details[0].data["candidate_groups"]
    ] == [
        ["同类资产A", "同类资产B"],
        ["其他资产C", "其他资产D"],
    ]


def test_asset_difference_refinement_lists_contract_differences_when_total_matches_asset_total_gap():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1501.04.05.01.DK20260531001", "流动资金贷款一号", Decimal("300")),
        ValuationRow("1541.01.CC8240D4", "丰润致远债权还款协议书", Decimal("500")),
    ]
    repo.dm_project_invest_refinements[("P1", "DK20260531001")] = {"pin_acbalance": Decimal("250")}
    repo.project_invest_balances[("P1", "CC8240D4")] = Decimal("450")

    results = ReconcileEngine(repo).run("2026-05-31")

    assert results[0].difference == Decimal("-100")
    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "已解释"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["difference_total"] == "-100"
    assert detail.data["specific_reason"] == "\n".join(
        [
            "①流动资金贷款一号贷款合同：FA科目余额与AM投融资余额有差异，差异值-50",
            "②丰润致远债权还款协议书财产权合同：FA科目余额与AM投融资余额有差异，差异值-50",
        ]
    )
    assert [row["asset_type"] for row in detail.data["rows"]] == ["贷款合同", "财产权合同"]


def test_asset_difference_refinement_does_not_duplicate_contract_suffix():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1303.01.01.DK20260601001", "园区流动资金贷款", Decimal("300")),
        ValuationRow("1541.01.CQ20260601001", "建工应收账款财产权", Decimal("500")),
    ]
    repo.dm_project_invest_refinements[("P1", "DK20260601001")] = {"pin_acbalance": Decimal("250")}
    repo.project_invest_balances[("P1", "CQ20260601001")] = Decimal("450")

    results = ReconcileEngine(repo).run("2026-05-31")

    detail = results[0].details[-1]
    assert detail.data["specific_reason"] == "\n".join(
        [
            "①园区流动资金贷款合同：FA科目余额与AM投融资余额有差异，差异值-50",
            "②建工应收账款财产权合同：FA科目余额与AM投融资余额有差异，差异值-50",
        ]
    )


def test_asset_difference_refinement_reports_unclear_when_contract_difference_is_partial():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("850"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1303.01.01.ZQ20260531001", "债权贷款一号", Decimal("300")),
        ValuationRow("1541.01.CC8240D4", "丰润致远债权还款协议书", Decimal("500")),
    ]
    repo.dm_project_invest_refinements[("P1", "ZQ20260531001")] = {"pin_acbalance": Decimal("250")}
    repo.project_invest_balances[("P1", "CC8240D4")] = Decimal("500")

    results = ReconcileEngine(repo).run("2026-05-31")

    assert results[0].difference == Decimal("-150")
    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "未解释"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["difference_total"] == "-50"
    assert detail.data["specific_reason"] == "暂不明确具体资产差异，但贷款合同，FA科目余额与AM投融资余额有差异，差异值-50"


def test_asset_difference_refinement_contracts_do_not_use_main_difference_as_full_match():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("900"))]
    repo.asset_total["P1"] = Decimal("1700")
    repo.valuation["P1"] = [
        ValuationRow("1303.01.01.DK20260601001", "园区流动资金贷款", Decimal("500")),
        ValuationRow("1541.01.CQ20260601001", "建工应收账款财产权", Decimal("500")),
    ]
    repo.dm_project_invest_refinements[("P1", "DK20260601001")] = {"pin_acbalance": Decimal("560")}
    repo.project_invest_balances[("P1", "CQ20260601001")] = Decimal("540")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("100")
    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "未解释"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["asset_total_gap"] == "-700"
    assert detail.data["difference_total"] == "100"
    assert detail.data["specific_reason"] == "暂不明确具体资产差异，但贷款/财产权合同，FA科目余额与AM投融资余额有差异，差异值100"


def test_asset_difference_refinement_uses_reverse_repo_amount_when_total_matches_asset_total_gap():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("300")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("200")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("-100")
    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "已解释"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["difference_total"] == "-100"
    assert detail.data["specific_reason"] == "①逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值-100"
    assert detail.data["rows"] == [
        {
            "index": "①",
            "asset_type": "逆回购",
            "asset_name": "逆回购",
            "account_code": "1111.12.34.01",
            "account_name": "质押式逆回购",
            "pact_id": "",
            "market_value": "300",
            "project_invest_balance": "200",
            "difference": "-100",
            "check_table": "assman_reg.ex_pledge_back",
            "reason": "逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值-100",
        }
    ]


def test_asset_difference_refinement_uses_bond_dm_amount_when_bond_group_still_overflows():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1015"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1101.02.55.01.ZQ001", "23苏城投MTN001", Decimal("40")),
        ValuationRow("1101.02.55.01.ZQ002", "23苏城投MTN002", Decimal("35")),
        ValuationRow("1101.02.55.01.ZQ003", "23苏城投MTN003", Decimal("30")),
    ]
    repo.security_balance_amounts["P1"] = [
        {"stock_code": "ZQ001", "security_name": "23苏城投MTN001", "amount": Decimal("40")},
        {"stock_code": "ZQ002", "security_name": "23苏城投MTN002", "amount": Decimal("20")},
        {"stock_code": "ZQ003", "security_name": "23苏城投MTN003", "amount": Decimal("30")},
        {"stock_code": "ZQ004", "security_name": "23苏城投MTN004", "amount": Decimal("30")},
    ]

    results = ReconcileEngine(repo, max_combination_rows=2).run("2026-06-01")

    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.match_type == "combination_overflow"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["difference_total"] == "15"
    assert detail.data["specific_reason"] == "①多个债券：FA债券本金科目余额与DM证券余额有差异，差异值15"
    assert detail.data["rows"] == [
        {
            "index": "①",
            "asset_type": "债券",
            "asset_name": "23苏城投MTN002",
            "account_code": "1101.02.55.01.ZQ002",
            "account_name": "23苏城投MTN002",
            "pact_id": "",
            "security_code": "ZQ002",
            "market_value": "35",
            "project_invest_balance": "20",
            "difference": "-15",
            "check_table": "dm.fa_security_balance_zgxg_dm",
            "reason": "23苏城投MTN002债券：FA债券本金科目余额与DM证券余额有差异，债券代码ZQ002，差异值-15",
        },
        {
            "index": "②",
            "asset_type": "债券",
            "asset_name": "23苏城投MTN004",
            "account_code": "",
            "account_name": "23苏城投MTN004",
            "pact_id": "",
            "security_code": "ZQ004",
            "market_value": "0",
            "project_invest_balance": "30",
            "difference": "30",
            "check_table": "dm.fa_security_balance_zgxg_dm",
            "reason": "23苏城投MTN004债券：FA估值表缺少该债券，债券代码ZQ004，DM证券余额30",
        },
    ]


def test_asset_difference_refinement_summarizes_multiple_bond_dm_differences_when_partial():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("900"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1501.01.55.01.ZQ001", "24产业债001", Decimal("40")),
        ValuationRow("1501.01.55.01.ZQ002", "24产业债002", Decimal("35")),
        ValuationRow("1501.01.55.01.ZQ003", "24产业债003", Decimal("30")),
    ]
    repo.security_balance_amounts["P1"] = [
        {"stock_code": "ZQ001", "security_name": "24产业债001", "amount": Decimal("20")},
        {"stock_code": "ZQ002", "security_name": "24产业债002", "amount": Decimal("5")},
        {"stock_code": "ZQ003", "security_name": "24产业债003", "amount": Decimal("30")},
    ]

    results = ReconcileEngine(repo, max_combination_rows=2).run("2026-06-01")

    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "组合候选过多"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["difference_total"] == "-50"
    assert detail.data["specific_reason"] == "暂不明确具体资产差异，但多个债券，FA债券本金科目余额与DM证券余额有差异，差异值-50"
    assert [row["asset_name"] for row in detail.data["rows"]] == ["24产业债001", "24产业债002"]


def test_asset_difference_bond_dm_refinement_runs_when_combination_is_not_overflow():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("875"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1101.02.55.01.ZQ001", "23苏城投MTN001", Decimal("80")),
        ValuationRow("1101.02.55.01.ZQ002", "23苏城投MTN002", Decimal("70")),
        ValuationRow("1101.02.55.01.ZQ003", "23苏城投MTN003", Decimal("50")),
    ]
    repo.security_balance_amounts["P1"] = [
        {"stock_code": "ZQ001", "security_name": "23苏城投MTN001", "amount": Decimal("20")},
        {"stock_code": "ZQ002", "security_name": "23苏城投MTN002", "amount": Decimal("30")},
        {"stock_code": "ZQ003", "security_name": "23苏城投MTN003", "amount": Decimal("25")},
    ]

    results = ReconcileEngine(repo, max_combination_rows=60).run("2026-06-03")

    assert results[0].valuation_match.match_type == "none"
    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "已解释"
    detail = results[0].details[-1]
    assert detail.data["difference_total"] == "-125"
    assert detail.data["specific_reason"] == "①多个债券：FA债券本金科目余额与DM证券余额有差异，差异值-125"
    assert len(detail.data["rows"]) == 3


def test_asset_difference_full_match_with_zero_remaining_stops_at_asset_difference():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("900"), Decimal("500"))]
    repo.asset_total["P1"] = Decimal("900")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("300")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("400")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("100")
    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == ["asset_gap", "asset_difference_refinement"]
    assert results[0].details[-1].data["remaining_difference"] == "0"
    assert results[0].details[-1].data["specific_reason"] == "①逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值100"


def test_asset_difference_full_match_continues_to_positive_repo_with_remaining_difference():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("850"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("900")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("300")),
        ValuationRow("2111.12.34.01.RP2026060101", "卖出回购金融资产款", Decimal("200")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("400")
    repo.positive_repo_business_amounts["P1"] = Decimal("150")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("150")
    assert results[0].difference_reason == "资产差异 + 负债及权益科目差异"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == [
        "asset_gap",
        "asset_difference_refinement",
        "liability_equity",
    ]
    assert results[0].details[1].data["remaining_difference"] == "50"
    assert results[0].details[2].data["match_target"] == "50"
    assert results[0].details[2].data["specific_reason"] == (
        "①逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值100\n"
        "②正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值50"
    )
    assert results[0].details[2].data["rows"][0]["index"] == "②"


def test_asset_difference_followup_multiple_liability_combinations_keeps_existing_logic():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("850"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("900")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("300")),
        ValuationRow("2209.01.01.01.A", "应付管理费A", Decimal("20")),
        ValuationRow("2209.01.01.01.B", "应付托管费B", Decimal("30")),
        ValuationRow("2221.01.01.01.C", "应交税费C", Decimal("10")),
        ValuationRow("2221.01.01.01.D", "其他应付款D", Decimal("40")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("400")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("150")
    assert results[0].difference_reason == "资产差异 + 负债及权益科目缺失"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == [
        "asset_gap",
        "asset_difference_refinement",
        "liability_equity",
    ]
    assert results[0].details[1].data["remaining_difference"] == "50"
    assert results[0].details[2].data["match_type"] == "combination"
    assert "candidate_groups" not in results[0].details[2].data


def test_combined_asset_bond_and_positive_repo_specific_reason_numbers_are_continuous():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("420"), Decimal("470"), Decimal("0"))]
    repo.fa4001["P1"] = Decimal("0")
    repo.asset_total["P1"] = Decimal("520")
    repo.valuation["P1"] = [
        ValuationRow("1101.02.55.01.ZQ001", "23苏城投MTN001", Decimal("80")),
        ValuationRow("1101.02.55.01.ZQ002", "23苏城投MTN002", Decimal("70")),
        ValuationRow("2111.12.34.01.RP2026060301", "卖出回购金融资产款", Decimal("200")),
    ]
    repo.security_balance_amounts["P1"] = [
        {"stock_code": "ZQ001", "security_name": "23苏城投MTN001", "amount": Decimal("30")},
        {"stock_code": "ZQ002", "security_name": "23苏城投MTN002", "amount": Decimal("20")},
    ]
    repo.positive_repo_business_amounts["P1"] = Decimal("150")

    results = ReconcileEngine(repo, max_combination_rows=60).run("2026-06-03")

    assert results[0].difference_reason == "资产差异 + 负债及权益科目差异"
    assert results[0].match_status == "已解释"
    assert results[0].details[2].data["specific_reason"] == (
        "①多个债券：FA债券本金科目余额与DM证券余额有差异，差异值-100\n"
        "②正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值50"
    )


def test_asset_difference_full_match_keeps_combined_type_when_followup_unresolved():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("850"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("900")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("300")),
        ValuationRow("2111.12.34.01.RP2026060101", "卖出回购金融资产款", Decimal("20")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("400")
    repo.positive_repo_business_amounts["P1"] = Decimal("0")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("150")
    assert results[0].difference_reason == "资产差异 + 负债及权益科目差异"
    assert results[0].match_status == "未解释"
    assert [detail.kind for detail in results[0].details] == [
        "asset_gap",
        "asset_difference_refinement",
        "liability_equity",
    ]
    assert results[0].details[1].data["remaining_difference"] == "50"
    assert results[0].details[2].data["specific_reason"] == (
        "①逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值100\n"
        "②暂不明确具体负债及权益科目差异，但正回购，FA科目余额与存续回购业务表正回购金额有差异，差异值20"
    )
    assert results[0].details[2].data["rows"][0]["index"] == "②"


def test_asset_difference_full_match_continues_to_received_trust_with_remaining_difference():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("850"), Decimal("450"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("900")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("300")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("400")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("150")
    assert results[0].difference_reason == "资产差异 + 实收本金差异"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == [
        "asset_gap",
        "asset_difference_refinement",
        "received_trust",
    ]
    assert results[0].details[2].data["specific_reason"] == (
        "①逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值100\n"
        "②实收本金差异：FA 4001与c1000存在差异，差异值50"
    )
    assert results[0].details[2].data["refinement_rows"][0]["index"] == "②"


def test_asset_difference_full_match_keeps_received_trust_type_when_residual_positive_repo_matches():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("820"), Decimal("450"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("900")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("300")),
        ValuationRow("2111.12.34.01.RP2026060101", "卖出回购金融资产款", Decimal("100")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("400")
    repo.positive_repo_business_amounts["P1"] = Decimal("70")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("180")
    assert results[0].difference_reason == "资产差异 + 实收本金差异 + 负债及权益科目差异"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == [
        "asset_gap",
        "asset_difference_refinement",
        "received_trust",
        "liability_equity",
    ]
    assert results[0].details[3].data["specific_reason"] == (
        "①逆回购：FA科目余额与存续回购业务表逆回购金额有差异，差异值100\n"
        "②实收本金差异：FA 4001与c1000存在差异，差异值50\n"
        "③正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值30"
    )
    assert results[0].details[3].data["rows"][0]["index"] == "③"


def test_asset_difference_refinement_does_not_use_main_difference_as_full_match():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("900"))]
    repo.asset_total["P1"] = Decimal("1500")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("1000")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("1100")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("100")
    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "未解释"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["asset_total_gap"] == "-500"
    assert detail.data["difference_total"] == "100"
    assert detail.data["specific_reason"] == "暂不明确具体资产差异，但逆回购，FA科目余额与存续回购业务表逆回购金额有差异，差异值100"


def test_asset_difference_refinement_reports_unclear_when_reverse_repo_amount_is_partial():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("850"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1111.12.34.01.RG2026060101", "质押式逆回购", Decimal("300")),
    ]
    repo.reverse_repo_business_amounts["P1"] = Decimal("250")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("-150")
    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "未解释"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["difference_total"] == "-50"
    assert detail.data["specific_reason"] == "暂不明确具体资产差异，但逆回购，FA科目余额与存续回购业务表逆回购金额有差异，差异值-50"


def test_asset_difference_refinement_unclear_reason_uses_actual_contract_types():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("850"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1541.01.CC8240D4", "丰润致远债权还款协议书", Decimal("500")),
    ]
    repo.project_invest_balances[("P1", "CC8240D4")] = Decimal("450")

    results = ReconcileEngine(repo).run("2026-05-31")

    assert results[0].difference_reason == "资产差异"
    detail = results[0].details[-1]
    assert detail.kind == "asset_difference_refinement"
    assert detail.data["specific_reason"] == "暂不明确具体资产差异，但财产权合同，FA科目余额与AM投融资余额有差异，差异值-50"


def test_asset_difference_refinement_uses_default_unclear_reason_without_contract_difference():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("850"), Decimal("1000"))]
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1001.01.01.01.0002", "其他资产", Decimal("30")),
    ]

    results = ReconcileEngine(repo).run("2026-05-31")

    assert results[0].difference_reason == "资产差异"
    assert results[0].match_status == "未解释"
    assert results[0].details[-1].kind == "asset_difference_refinement"
    assert results[0].details[-1].data["specific_reason"] == "暂不明确具体资产差异"


def test_progress_logs_include_project_level_steps():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("5000000"), Decimal("20000000"))]
    repo.asset_total["P1"] = Decimal("20000000")
    repo.valuation["P1"] = [
        ValuationRow("1541.01.PACTA", "财产权A", Decimal("5000000")),
        ValuationRow("1541.01.PACTB", "财产权B", Decimal("5000000")),
    ]
    repo.project_invest_balances[("P1", "PACTA")] = Decimal("0")
    repo.project_invest_balances[("P1", "PACTB")] = Decimal("0")
    logs = []

    ReconcileEngine(
        repo,
        progress_logger=lambda message, progress, step: logs.append(message),
    ).run("2026-05-31")

    assert any("P1：读取估值表0004资产合计" in message for message in logs)
    assert any("P1：读取估值表资产端候选科目" in message for message in logs)
    assert any("P1：查询财产权合同投融资余额，合同PACTA" in message for message in logs)
    assert any("P1：合同PACTA：AM余额=0，估值=5000000，差异=-5000000" in message for message in logs)


def test_received_trust_error_when_c1000_differs_from_fa4001_by_main_difference():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("900"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "实收本金差异"
    assert results[0].match_status == "已解释"
    assert results[0].details[0].kind == "received_trust"
    assert results[0].details[0].data["specific_reason"] == "①实收本金差异：FA 4001与c1000存在差异，差异值100"
    assert results[0].details[0].data["c1000_balance"] == "400"
    assert results[0].details[0].data["fa_4001_balance"] == "500"


def test_received_trust_missing_when_main_difference_equals_fa4001():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("500"), Decimal("0"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "实收本金缺失"
    assert results[0].match_status == "已解释"
    assert results[0].details[0].kind == "received_trust"
    assert results[0].details[0].data["specific_reason"] == "①实收本金缺失：FA 4001科目余额500；原因：资负数据子系统-实收本金明细表无数据"


def test_received_trust_missing_requires_c1000_to_be_zero_when_difference_equals_fa4001():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("500"), Decimal("100"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference == Decimal("500")
    assert results[0].difference_reason == "负债及权益科目差异"
    assert results[0].match_status == "未解释"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "liability_equity"]
    assert results[0].details[0].data["received_trust_difference"] == "400"
    assert results[0].details[1].data["residual_difference"] == "100"
    assert results[0].details[1].data["specific_reason"] == (
        "①实收本金差异：FA 4001与c1000存在差异，差异值400\n"
        "②暂不明确具体负债及权益科目差异"
    )


def test_received_trust_missing_omits_report_reason_when_principal_report_exists():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("500"), Decimal("0"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.report_rows.add((("currency_report_24", "currency_detail_project_2_1_8"), "2026-04-30"))

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "实收本金缺失"
    assert results[0].details[0].data["specific_reason"] == "①实收本金缺失：FA 4001科目余额500"


def test_received_trust_duplicate_when_main_difference_equals_negative_fa4001():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("1500"), Decimal("1000"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "实收本金重复"
    assert results[0].match_status == "已解释"
    assert results[0].details[0].kind == "received_trust"
    assert results[0].details[0].data["specific_reason"] == "①实收本金重复：FA 4001科目余额500；原因：c1000疑似重复计入1次，重复金额500"
    assert results[0].details[0].data["repeat_count"] == "1"


def test_received_trust_duplicate_supports_multiple_repeat_count():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("2000"), Decimal("1500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")

    results = ReconcileEngine(repo).run("2026-06-12")

    assert results[0].difference_reason == "实收本金重复"
    assert results[0].match_status == "已解释"
    detail = results[0].details[0]
    assert detail.kind == "received_trust"
    assert detail.data["specific_reason"] == "①实收本金重复：FA 4001科目余额500；原因：c1000疑似重复计入2次，重复金额1000"
    assert detail.data["repeat_count"] == "2"
    assert detail.data["repeat_amount"] == "1000"
    assert detail.data["refinement_rows"][0]["check_result"] == "c1000为FA 4001科目余额的3倍，a0001-d0000等于重复金额的相反数"


def test_received_trust_duplicate_requires_integer_multiple_of_fa4001():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("1750"), Decimal("1250"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")

    results = ReconcileEngine(repo).run("2026-06-12")

    assert results[0].difference == Decimal("-750")
    assert results[0].difference_reason == "实收本金差异"
    assert results[0].match_status == "已解释"
    assert results[0].details[0].data["received_trust_difference"] == "-750"


def test_received_trust_duplicate_requires_c1000_to_be_twice_fa4001_when_difference_equals_negative_fa4001():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("1500"), Decimal("0"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference == Decimal("-500")
    assert results[0].difference_reason == "负债及权益科目差异"
    assert results[0].match_status == "未解释"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "liability_equity"]
    assert results[0].details[0].data["received_trust_difference"] == "500"
    assert results[0].details[1].data["residual_difference"] == "-1000"
    assert results[0].details[1].data["specific_reason"] == (
        "①实收本金差异：FA 4001与c1000存在差异，差异值500\n"
        "②暂不明确具体负债及权益科目差异"
    )


def test_received_trust_detail_reports_ta_dm_dws_total_mismatch():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("900"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.ta_dm_total["P1"] = Decimal("400")
    repo.ta_dws_total["P1"] = Decimal("500")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "实收本金差异"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "ta_total_mismatch"]
    assert results[0].details[-1].data["specific_reason"] == "①实收本金差异：FA 4001与c1000存在差异，差异值100；原因：DM表TA份额余额错误"
    assert results[0].details[-1].data["dm_total"] == "400"
    assert results[0].details[-1].data["dws_total"] == "500"


def test_received_trust_keeps_generic_specific_reason_when_ta_total_mismatch_amount_does_not_match_gap():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("900"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.ta_dm_total["P1"] = Decimal("480")
    repo.ta_dws_total["P1"] = Decimal("500")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "实收本金差异"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "ta_total_mismatch"]
    assert results[0].details[0].data["specific_reason"] == "①实收本金差异：FA 4001与c1000存在差异，差异值100"
    assert "specific_reason" not in results[0].details[-1].data
    assert results[0].details[-1].data["difference"] == "-20"


def test_received_trust_detail_reports_blank_dependent_ta_client_type_rows():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("900"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.ta_dm_total["P1"] = Decimal("500")
    repo.ta_dws_total["P1"] = Decimal("500")
    repo.ta_blank_client_type_rows["P1"] = [
        {
            "pact_id": "PACT1",
            "client_name": "客户A",
            "client_kind": "4",
            "client_kind_index": "",
            "spv_type": "SPV1",
            "ht_income": Decimal("30"),
            "share_amount": Decimal("70"),
            "amount": Decimal("100"),
        }
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "实收本金差异"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "ta_blank_client_type"]
    assert results[0].details[-1].data["specific_reason"] == "①实收本金差异：FA 4001与c1000存在差异，差异值100；原因：dm.ta_pact_survamt_day_zgxg_dm表中客户类型为空导致实收信托有误"
    assert results[0].details[-1].data["blank_client_type_total"] == "100"
    assert results[0].details[-1].data["rows"][0]["pact_id"] == "PACT1"
    assert results[0].details[-1].data["rows"][0]["client_kind_index"] == ""


def test_received_trust_detail_keeps_generic_reason_when_ta_checks_do_not_explain_gap():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("900"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.ta_dm_total["P1"] = Decimal("500")
    repo.ta_dws_total["P1"] = Decimal("500")
    repo.ta_blank_client_type_rows["P1"] = [
        {
            "pact_id": "PACT1",
            "client_name": "客户A",
            "client_kind": "5",
            "client_kind_index": "1",
            "spv_type": "",
            "ht_income": Decimal("10"),
            "share_amount": Decimal("20"),
            "amount": Decimal("30"),
        }
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "实收本金差异"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "ta_blank_client_type"]
    assert results[0].details[0].data["specific_reason"] == "①实收本金差异：FA 4001与c1000存在差异，差异值100"
    assert "specific_reason" not in results[0].details[-1].data
    assert results[0].details[-1].data["blank_client_type_total"] == "30"


def test_liability_equity_difference_uses_non_asset_valuation_rows_without_leaf_limit():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("1001.01.01.01.0001", "ignored asset", Decimal("50")),
        ValuationRow("4002", "其他收益", Decimal("50")),
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert repo.valuation_row_calls == [("P1", None, "1", False)]
    assert results[0].difference_reason == "负债及权益科目缺失"
    assert results[0].valuation_match.rows[0].account_code == "4002"
    assert results[0].details[0].data["specific_reason"] == "①负债及权益科目缺失：其他收益"


def test_liability_equity_matching_ignores_zero_prefixed_four_digit_summary_accounts():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("0001", "资产净值", Decimal("50")),
        ValuationRow("4002", "其他收益", Decimal("30")),
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "负债及权益科目差异"
    assert results[0].match_status == "未解释"
    assert results[0].valuation_match.match_type == "none"
    assert results[0].details[0].data["specific_reason"] == "暂不明确具体负债及权益科目差异"


def test_liability_equity_single_match_keeps_parent_account_candidates():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("2111", "卖出回购金融资产款", Decimal("50")),
        ValuationRow("2111.01.03.01.R001", "正回购本金", Decimal("10")),
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].valuation_match.match_type == "single"
    assert results[0].valuation_match.rows[0].account_code == "2111"


def test_liability_equity_combination_uses_leaf_rows_and_excludes_positive_repo_interest():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("2111", "卖出回购金融资产款", Decimal("20")),
        ValuationRow("2111.01", "上交所", Decimal("20")),
        ValuationRow("2111.01.03.02.R001", "正回购应计利息", Decimal("10")),
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].valuation_match.match_type == "none"


def test_liability_equity_uses_fourth_level_group_combination_after_full_leaf_overflow():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("930"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("2209.02.01.01.A", "同类负债A", Decimal("30")),
        ValuationRow("2209.02.01.01.B", "同类负债B", Decimal("40")),
        ValuationRow("2221.05.01.01.C", "其他负债C", Decimal("10")),
        ValuationRow("2221.05.01.01.D", "其他负债D", Decimal("20")),
    ]

    results = ReconcileEngine(repo, max_combination_rows=3).run("2026-06-01")

    assert results[0].difference_reason == "负债及权益科目缺失"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.match_type == "combination"
    assert results[0].valuation_match.message == "分类组合命中：2209.02.01.01"
    assert [row.account_code for row in results[0].valuation_match.rows] == [
        "2209.02.01.01.A",
        "2209.02.01.01.B",
    ]
    assert results[0].details[0].data["match_message"] == "分类组合命中：2209.02.01.01"


def test_liability_equity_main_difference_with_multiple_candidate_combinations_is_unknown():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("2209.01.01.01.A", "应付管理费A", Decimal("20")),
        ValuationRow("2209.01.01.01.B", "应付托管费B", Decimal("30")),
        ValuationRow("2221.01.01.01.C", "应交税费C", Decimal("10")),
        ValuationRow("2221.01.01.01.D", "其他应付款D", Decimal("40")),
    ]

    results = ReconcileEngine(repo).run("2026-06-03")

    assert results[0].difference == Decimal("50")
    assert results[0].difference_reason == "负债及权益科目缺失 + 暂无法确定"
    assert results[0].match_status == "候选不唯一"
    assert results[0].valuation_match.match_type == "ambiguous_combination"
    assert results[0].details[0].kind == "liability_equity"
    assert results[0].details[0].data["specific_reason"] == "候选不唯一"
    assert len(results[0].details[0].data["candidate_groups"]) == 2
    assert [
        [row["account_name"] for row in group["rows"]]
        for group in results[0].details[0].data["candidate_groups"]
    ] == [
        ["应付管理费A", "应付托管费B"],
        ["应交税费C", "其他应付款D"],
    ]


def test_liability_equity_residual_difference_multiple_combinations_keeps_existing_logic():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("510")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("2209.01.01.01.A", "应付管理费A", Decimal("10")),
        ValuationRow("2209.01.01.01.B", "应付托管费B", Decimal("30")),
        ValuationRow("2221.01.01.01.C", "应交税费C", Decimal("15")),
        ValuationRow("2221.01.01.01.D", "其他应付款D", Decimal("25")),
    ]

    results = ReconcileEngine(repo).run("2026-06-03")

    assert results[0].difference == Decimal("50")
    assert results[0].details[1].data["residual_difference"] == "40"
    assert results[0].difference_reason == "负债及权益科目缺失"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.match_type == "combination"


def test_liability_equity_duplicate_when_non_asset_rows_match_negative_difference():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("1050"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("4002", "其他收益", Decimal("50"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "负债及权益科目重复"
    assert results[0].valuation_match.rows[0].account_code == "4002"
    assert results[0].details[0].data["specific_reason"] == "①负债及权益科目重复：其他收益"


def test_liability_equity_matches_negative_3001_common_payable_as_absolute_amount():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("1050"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [
        ValuationRow("3001.02", "应付账款共同类", Decimal("-50")),
        ValuationRow("3001.03", "应收账款共同类", Decimal("50")),
    ]

    results = ReconcileEngine(repo).run("2026-06-12")

    assert results[0].difference_reason == "负债及权益科目重复"
    assert results[0].match_status == "已解释"
    assert results[0].valuation_match.rows[0].account_code == "3001.02"
    assert results[0].valuation_match.rows[0].market_value == Decimal("50")
    assert results[0].details[0].data["specific_reason"] == (
        "①应付账款_共同类重复：应付账款共同类；原因：3001共同类科目为负数，按绝对值参与负债权益核对"
    )


def test_liability_equity_positive_repo_match_sets_specific_reason():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("2111.12.34.01.RP001", "卖出回购金融资产款", Decimal("50"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "负债及权益科目缺失"
    assert results[0].details[0].data["specific_reason"] == "①正回购缺失：卖出回购金融资产款；原因：正回购差异"


def test_liability_equity_difference_when_non_asset_rows_do_not_match():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("4002", "其他收益", Decimal("30"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "负债及权益科目差异"
    assert results[0].match_status == "未解释"
    assert results[0].details[0].data["specific_reason"] == "暂不明确具体负债及权益科目差异"


def test_liability_equity_difference_uses_positive_repo_amount_when_total_matches_main_difference():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("500"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("2111.12.34.01.RP2026060101", "卖出回购金融资产款", Decimal("200"))]
    repo.positive_repo_business_amounts["P1"] = Decimal("150")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference == Decimal("50")
    assert results[0].difference_reason == "负债及权益科目差异"
    assert results[0].match_status == "已解释"
    detail = results[0].details[0]
    assert detail.kind == "liability_equity"
    assert detail.data["specific_reason"] == "①正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值50"
    assert detail.data["repo_difference_total"] == "50"
    assert detail.data["rows"] == [
        {
            "index": "①",
            "account_type": "正回购",
            "account_name": "正回购",
            "account_code": "2111.12.34.01",
            "account_tail": "",
            "market_value": "200",
            "direction": "差异",
            "check_result": "金额差异",
            "reason": "正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值50",
            "business_amount": "150",
        }
    ]


def test_received_trust_difference_uses_residual_amount_for_liability_equity_match():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("4002", "其他收益", Decimal("50"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "负债及权益科目重复"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "liability_equity"]
    assert results[0].details[0].data["received_trust_difference"] == "100"
    assert results[0].details[1].data["match_target"] == "50"
    assert results[0].details[1].data["residual_difference"] == "-50"
    assert results[0].details[1].data["specific_reason"] == "①实收本金差异：FA 4001与c1000存在差异，差异值100\n②负债及权益科目重复：其他收益"
    assert results[0].valuation_match.rows[0].account_code == "4002"


def test_received_trust_residual_positive_repo_match_sets_specific_reason():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("2111.12.34.01.RP001", "卖出回购金融资产款", Decimal("50"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "负债及权益科目重复"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "liability_equity"]
    assert results[0].details[1].data["residual_difference"] == "-50"
    assert results[0].details[1].data["specific_reason"] == "①实收本金差异：FA 4001与c1000存在差异，差异值100\n②正回购重复：卖出回购金融资产款；原因：正回购差异"


def test_received_trust_difference_residual_unmatched_is_liability_equity_difference():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("4002", "其他收益", Decimal("30"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "负债及权益科目差异"
    assert results[0].match_status == "未解释"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "liability_equity"]
    assert results[0].details[1].data["residual_difference"] == "-50"
    assert results[0].details[1].data["specific_reason"] == "①实收本金差异：FA 4001与c1000存在差异，差异值100\n②暂不明确具体负债及权益科目差异"


def test_received_trust_residual_positive_repo_amount_match_sets_specific_reason():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("1000"), Decimal("950"), Decimal("400"))]
    repo.fa4001["P1"] = Decimal("500")
    repo.asset_total["P1"] = Decimal("1000")
    repo.valuation["P1"] = [ValuationRow("2111.12.34.01.RP2026060101", "卖出回购金融资产款", Decimal("200"))]
    repo.positive_repo_business_amounts["P1"] = Decimal("250")

    results = ReconcileEngine(repo).run("2026-06-01")

    assert results[0].difference_reason == "负债及权益科目差异"
    assert results[0].match_status == "已解释"
    assert [detail.kind for detail in results[0].details] == ["received_trust", "liability_equity"]
    assert results[0].details[1].data["residual_difference"] == "-50"
    assert results[0].details[1].data["specific_reason"] == (
        "①实收本金差异：FA 4001与c1000存在差异，差异值100\n"
        "②正回购：FA科目余额与存续回购业务表正回购金额有差异，差异值-50"
    )


def test_asset_missing_ignores_am_check_when_account_level_is_not_target_level():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [ValuationRow("1001.01.01.01.0002", "Asset A", Decimal("10"))]
    repo.pact_assets[("P1", "Asset A")] = [PactAssetRow("P1", "Asset A", "9999")]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert [detail.kind for detail in results[0].details] == ["asset_gap", "asset_missing_refinement"]
    assert results[0].details[-1].data["specific_reason"] == "①其他资产缺失：1001.01.01.01.0002 Asset A"


def test_asset_missing_sets_fa_am_mismatch_for_target_level_when_stockcode_differs():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [ValuationRow("1101.05.03.01.0002", "Asset A_估值后缀", Decimal("10"))]
    repo.pact_assets[("P1", "Asset A")] = [PactAssetRow("P1", "Asset A", "9999", "PACT1")]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert [detail.kind for detail in results[0].details] == ["asset_gap", "fa_am", "asset_missing_refinement"]
    assert results[0].details[1].data["specific_reason"] == "FA与AM标的不一致"
    assert results[0].details[1].data["fa_account_name"] == "Asset A_估值后缀"
    assert results[0].details[1].data["am_asset_name"] == "Asset A"
    assert results[0].details[1].data["am_stock_code"] == "9999"
    assert results[0].details[-1].data["specific_reason"] == "①特定目的载体缺失：Asset A_估值后缀；原因：FA和AM标的不一致"


def test_asset_missing_refinement_keeps_multiple_spv_stock_mismatch_script_fields():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("80"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [
        ValuationRow("1101.05.04.01.0001", "银行理财A_估值后缀", Decimal("10")),
        ValuationRow("1101.05.05.01.0002", "保险理财B_估值后缀", Decimal("10")),
    ]
    repo.pact_assets[("P1", "银行理财A")] = [PactAssetRow("P1", "银行理财A", "9999", "PACT_A")]
    repo.pact_assets[("P1", "保险理财B")] = [PactAssetRow("P1", "保险理财B", "8888", "PACT_B")]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].details[-1].data["specific_reason"] == "\n".join(
        [
            "①特定目的载体缺失：银行理财A_估值后缀；原因：FA和AM标的不一致",
            "②特定目的载体缺失：保险理财B_估值后缀；原因：FA和AM标的不一致",
        ]
    )
    assert results[0].details[-1].data["rows"][0]["am_stock_code"] == "9999"
    assert results[0].details[-1].data["rows"][0]["pact_id"] == "PACT_A"
    assert results[0].details[-1].data["rows"][1]["am_stock_code"] == "8888"
    assert results[0].details[-1].data["rows"][1]["pact_id"] == "PACT_B"


def test_asset_name_match_keeps_parentheses_and_ignores_only_suffix():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [
        ValuationRow(
            "1101.05.03.01.0002",
            "江苏信托·金信添利系列集合资金信托计划（JXTL009）_202604160001",
            Decimal("10"),
        )
    ]
    repo.pact_assets[("P1", "江苏信托·金信添利系列集合资金信托计划（JXTL009）")] = [
        PactAssetRow("P1", "江苏信托·金信添利系列集合资金信托计划（JXTL009）", "9999", "PACT1")
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].details[1].data["specific_reason"] == "FA与AM标的不一致"
    assert results[0].details[1].data["am_asset_name"] == "江苏信托·金信添利系列集合资金信托计划（JXTL009）"
    assert results[0].details[-1].data["specific_reason"] == (
        "①特定目的载体缺失：江苏信托·金信添利系列集合资金信托计划（JXTL009）_202604160001；原因：FA和AM标的不一致"
    )


def test_asset_name_match_does_not_ignore_different_parentheses():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [
        ValuationRow(
            "1101.05.03.01.0002",
            "江苏信托·金信添利系列集合资金信托计划（JXTL010）_202604160001",
            Decimal("10"),
        )
    ]
    repo.pact_assets[("P1", "江苏信托·金信添利系列集合资金信托计划（JXTL009）")] = [
        PactAssetRow("P1", "江苏信托·金信添利系列集合资金信托计划（JXTL009）", "9999", "PACT1")
    ]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].details[1].data["specific_reason"] == "AM标的缺失"
    assert results[0].details[-1].data["specific_reason"] == (
        "①特定目的载体缺失：江苏信托·金信添利系列集合资金信托计划（JXTL010）_202604160001；原因：AM标的缺失"
    )


def test_asset_missing_sets_am_target_missing_for_target_level_without_name_match():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [ValuationRow("1101.05.03.01.0002", "Asset A", Decimal("10"))]
    repo.pact_assets[("P1", "Completely Different")] = [PactAssetRow("P1", "Completely Different", "9999")]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert [detail.kind for detail in results[0].details] == ["asset_gap", "am_missing", "asset_missing_refinement"]
    assert results[0].details[1].data["specific_reason"] == "AM标的缺失"
    assert results[0].details[1].data["fa_account_code"] == "1101.05.03.01.0002"
    assert results[0].details[1].data["fa_account_name"] == "Asset A"
    assert results[0].details[-1].data["specific_reason"] == "①特定目的载体缺失：Asset A；原因：AM标的缺失"


def test_asset_missing_sets_am_target_missing_for_150103_spv_account():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [ValuationRow("1501.03.12.01.SPV001", "SPV Asset", Decimal("10"))]
    repo.pact_assets[("P1", "Completely Different")] = [PactAssetRow("P1", "Completely Different", "SPV001")]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert [detail.kind for detail in results[0].details] == ["asset_gap", "am_missing", "asset_missing_refinement"]
    assert results[0].details[1].data["specific_reason"] == "AM标的缺失"
    assert results[0].details[1].data["fa_account_code"] == "1501.03.12.01.SPV001"
    assert results[0].details[1].data["expected_account_level"] == "1501.03.12.01"
    assert results[0].details[-1].data["specific_reason"] == "①特定目的载体缺失：SPV Asset；原因：AM标的缺失"


def test_asset_missing_am_target_missing_shows_actual_spv_account_level():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [ValuationRow("1101.05.01.01.0002", "Asset A", Decimal("10"))]

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].details[1].kind == "am_missing"
    assert results[0].details[1].data["expected_account_level"] == "1101.05.01.01"


def test_asset_missing_sets_project_invest_zero_when_contract_balance_is_zero():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [ValuationRow("1101.05.03.01.0002", "Asset A", Decimal("10"))]
    repo.pact_assets[("P1", "Asset A")] = [PactAssetRow("P1", "Asset A", "0002", "PACT1")]
    repo.project_invest_balances[("P1", "PACT1")] = Decimal("0")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert [detail.kind for detail in results[0].details] == ["asset_gap", "project_invest_balance", "asset_missing_refinement"]
    assert results[0].details[1].data["specific_reason"] == "合同投融资余额为0但FA科目余额不为0"
    assert results[0].details[1].data["pact_id"] == "PACT1"
    assert results[0].details[1].data["project_invest_balance"] == "0"
    assert results[0].details[1].data["fa_market_value"] == "10"
    assert results[0].details[-1].data["specific_reason"] == "①特定目的载体缺失：Asset A；原因：合同投融资余额为0但FA科目余额不为0"


def test_asset_missing_prompts_sql_check_when_am_and_contract_balance_are_normal():
    repo = FakeRepo()
    repo.projects = [ProjectBalance("P1", "Project", Decimal("90"), Decimal("100"))]
    repo.asset_total["P1"] = Decimal("100")
    repo.valuation["P1"] = [ValuationRow("1101.05.03.01.0002", "Asset A", Decimal("10"))]
    repo.pact_assets[("P1", "Asset A")] = [PactAssetRow("P1", "Asset A", "0002", "PACT1")]
    repo.project_invest_balances[("P1", "PACT1")] = Decimal("20")

    results = ReconcileEngine(repo).run("2026-04-30")

    assert results[0].difference_reason == "资产缺失"
    assert results[0].details[1].kind == "project_invest_balance"
    assert results[0].details[1].data["specific_reason"] == ""
    assert results[0].details[1].data["project_invest_balance"] == "20"
    assert results[0].details[-1].data["specific_reason"] == (
        "①特定目的载体缺失：Asset A；原因：该特定目的载体在dm.am_projinvest_spv_zgxg_dm不存在或余额为0"
    )
