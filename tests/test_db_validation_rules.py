from datetime import date
import re

from auto_check.db_validation.rules.basic import run_basic_rules
from auto_check.db_validation.rules.common import area_not_county_level


def test_zg04_share_cross_period_uses_projshare_field():
    current_rows = [
        {
            "projcode": "P1",
            "areacode": "320000",
            "clientkind": "5",
            "moneytype": "CNY",
            "currraiseamt": "10",
            "curraiseshare": "10",
            "curcashshare": "20",
            "projshare": "90",
        }
    ]
    previous_rows = [
        {
            "projcode": "P1",
            "areacode": "320000",
            "clientkind": "5",
            "moneytype": "CNY",
            "projshare": "100",
        }
    ]

    rows = run_basic_rules("ZG04", date(2026, 5, 31), current_rows, previous_rows)

    assert rows == []


def test_area_rule_uses_legacy_reject_list_not_suffix_only():
    assert area_not_county_level("110000")
    assert area_not_county_level("110100")
    assert area_not_county_level("320100")

    assert not area_not_county_level("120100")
    assert not area_not_county_level("133100")
    assert not area_not_county_level("310100")


def test_zg01_remaining_legacy_rules_are_triggerable_from_database_rows():
    rows = run_basic_rules(
        "ZG01",
        date(2026, 5, 31),
        [
            {"projcode": "P1", "projname": "正常产品一号", "projpredate": "", "earlystopflg": "1"},
            {"projcode": "P3", "projname": "正常产品三号", "creditflg": "1", "creditform": "1", "credittype": "2"},
            {"projcode": "P4", "projname": "正常产品四号", "runmode": "1", "redeemflg": "1"},
            {"projcode": "ABCDEFG25X", "projname": "正常产品五号", "raisebegdate": "2026-01-01"},
            {"projcode": "P7", "projname": "正常产品七号", "levelflg": "1", "source": "2"},
            {"projcode": "P8", "projname": "正常产品八号", "depoutorgcode": "某银行上海分行"},
            {"projcode": "P9", "projname": "正常产品九号", "depoutorgcode": "某银行总行", "depinorgcode": ""},
        ],
        [],
    )

    assert {
        "Zg01_Rule1",
        "Zg01_Rule3",
        "Zg01_Rule4",
        "Zg01_Rule5",
        "Zg01_Rule7",
        "Zg01_Rule8",
        "Zg01_Rule9",
    }.issubset({_result_rule_id(row) for row in rows})


def test_zg02_zg03_legacy_rules_are_triggerable_from_database_rows():
    zg02_rows = run_basic_rules(
        "ZG02",
        date(2026, 5, 31),
        [
            {"projcode": "P1", "moneytype": "CNY", "areacode": "000100", "clientkind": "1", "raiseamt": "100"},
            {"projcode": "P1", "moneytype": "BWB", "areacode": "000100", "clientkind": "1", "raiseamt": "90"},
        ],
        [],
    )
    assert {"Zg02_Rule1", "Zg02_Rule2"}.issubset({_result_rule_id(row) for row in zg02_rows})

    zg03_rows = run_basic_rules(
        "ZG03",
        date(2026, 5, 31),
        [
            {"projcode": "P2", "moneytype": "CNY", "clientincome": "100", "clientincomecny": "600000001", "clientrate": "11"},
            {"projcode": "P2", "moneytype": "BWB", "clientincome": "80", "clientincomecny": "80", "clientrate": ""},
        ],
        [],
    )
    assert {"Zg03_Rule1", "Zg03_Rule2"}.issubset({_result_rule_id(row) for row in zg03_rows})


def test_zg05_legacy_balance_rules_are_triggerable_from_database_rows():
    rows = run_basic_rules(
        "ZG05",
        date(2026, 5, 31),
        [
            {"projcode": "P1", "moneytype": "CNY", "datetype": "1", "a0001": "100"},
            {"projcode": "P1", "moneytype": "CNY", "datetype": "2", "a0001": "80"},
            {"projcode": "P1", "moneytype": "BWB", "datetype": "3", "a0001": "90"},
            {"projcode": "P2", "moneytype": "BWB", "datetype": "3", "a5100": "100"},
            {"projcode": "P3", "moneytype": "BWB", "datetype": "3", "a5271": "100"},
        ],
        [],
        related_rows={
            "ZG07": [{"projcode": "P2", "iouamtcny_tz": "80"}],
            "ZG08": [{"projcode": "P3", "debtorproj": "A5200", "riverprojtype": "1", "sharamtcny": "70"}],
        },
    )
    assert {"Zg05_Rule1", "Zg05_Rule2", "Zg05_Rule3", "Zg05_Rule4"}.issubset({_result_rule_id(row) for row in rows})


def test_zg05_currency_rules_ignore_metadata_alias_columns():
    rows = run_basic_rules(
        "ZG05",
        date(2026, 5, 31),
        [
            {
                "projcode": "P1",
                "产品代码": "P1",
                "moneytype": "CNY",
                "币种": "CNY",
                "datetype": "1",
                "数据类型": "1",
                "a0001": "100",
                "A0001_资产合计": "100",
            },
            {
                "projcode": "P1",
                "产品代码": "P1",
                "moneytype": "CNY",
                "币种": "CNY",
                "datetype": "2",
                "数据类型": "2",
                "a0001": "100",
                "A0001_资产合计": "100",
            },
            {
                "projcode": "P1",
                "产品代码": "P1",
                "moneytype": "BWB",
                "币种": "BWB",
                "datetype": "3",
                "数据类型": "3",
                "a0001": "100",
                "A0001_资产合计": "100",
            },
        ],
        [],
    )

    assert {"Zg05_Rule1", "Zg05_Rule2"}.isdisjoint({_result_rule_id(row) for row in rows})


def test_zg05_spv_rule_uses_legacy_zg05_zg08_counterparty_mapping():
    rows = run_basic_rules(
        "ZG05",
        date(2026, 5, 31),
        [
            {"projcode": "P1", "moneytype": "BWB", "datetype": "3", "a5271": "100", "a5200": "0"},
        ],
        [],
        related_rows={
            "ZG08": [
                {"projcode": "P1", "debtorproj": "A5200", "riverprojtype": "1", "sharamtcny": "100"},
                {"projcode": "P1", "debtorproj": "A5200", "riverprojtype": "2", "sharamtcny": "30"},
            ]
        },
    )

    assert "Zg05_Rule4" not in {_result_rule_id(row) for row in rows}


def test_zg13_area_rule_does_not_report_current_legacy_allowed_codes():
    rows = run_basic_rules(
        "ZG13",
        date(2026, 5, 31),
        [
            _zg13_row("P1", "91310000100019382F", "I1", areacode="120100", debtproj="A0000", qymoneycny="0"),
            _zg13_row("P2", "911201160587020562", "I2", areacode="133100", debtproj="A0000", qymoneycny="0"),
            _zg13_row("P3", "C1010511003703", "I3", areacode="310100", debtproj="A0000", qymoneycny="0"),
        ],
        [],
    )

    assert rows == []


def test_zg04_cash_amount_share_rule_is_legacy_one_way_check():
    rows = run_basic_rules(
        "ZG04",
        date(2026, 5, 31),
        [
            _zg04_row("P1", areacode="320101", clientkind="1", moneytype="BWB", curcashamt="100", curcashshare="0"),
            _zg04_row("P2", areacode="320101", clientkind="1", moneytype="BWB", curcashamt="0", curcashshare="5"),
        ],
        [],
    )

    details = [row.detail for row in rows if _result_rule_id(row) == "Zg04_Rule12"]
    assert not any("P1" in detail for detail in details)
    assert any("P2" in detail for detail in details)


def test_zg04_rule1_uses_legacy_principal_components_without_summary_or_cross_org_mix():
    rows = run_basic_rules(
        "ZG04",
        date(2026, 5, 31),
        [
            _zg04_row("P1", areacode="000000", clientkind="1", moneytype="BWB", projshare="100") | {"jgcode": "ORG1"},
            _zg04_row("P2", areacode="000000", clientkind="1", moneytype="BWB", projshare="100"),
        ],
        [],
        related_rows={
            "ZG05": [
                {"projcode": "P1", "jgcode": "ORG1", "moneytype": "BWB", "datetype": "3", "c1110": "100"},
                {"projcode": "P1", "jgcode": "ORG2", "moneytype": "BWB", "datetype": "3", "c1110": "50"},
                {"projcode": "P2", "moneytype": "BWB", "datetype": "3", "c1110": "60", "c1210": "40", "c1000": "100"},
            ]
        },
    )

    details = [row.detail for row in rows if _result_rule_id(row) == "Zg04_Rule1"]
    assert not any("P1" in detail for detail in details)
    assert not any("P2" in detail for detail in details)


def test_zg04_share_cross_period_treats_missing_previous_as_zero():
    rows = run_basic_rules(
        "ZG04",
        date(2026, 5, 31),
        [
            {
                "projcode": "P2",
                "areacode": "320000",
                "clientkind": "5",
                "moneytype": "CNY",
                "curraiseshare": "0",
                "curcashshare": "0",
                "projshare": "3000000",
            }
        ],
        [],
    )

    assert [row.mark.split("-")[-1] for row in rows] == ["Zg04_Rule2"]


def test_zg04_amount_cross_period_uses_legacy_thresholds_and_filters():
    rows = run_basic_rules(
        "ZG04",
        date(2026, 5, 31),
        [
            {
                "projcode": "P3",
                "areacode": "110000",
                "clientkind": "5",
                "moneytype": "CNY",
                "currraiseamt": "1257300000",
                "curcashamt": "1371026984.66",
                "projamt": "538141916.90",
            },
            {
                "projcode": "P4",
                "areacode": "000000",
                "clientkind": "5",
                "moneytype": "CNY",
                "currraiseamt": "1257300000",
                "curcashamt": "1371026984.66",
                "projamt": "538141916.90",
            },
        ],
        [
            {
                "projcode": "P3",
                "areacode": "110000",
                "clientkind": "5",
                "moneytype": "CNY",
                "projamt": "615277744.16",
            },
            {
                "projcode": "P4",
                "areacode": "000000",
                "clientkind": "5",
                "moneytype": "CNY",
                "projamt": "615277744.16",
            },
        ],
    )

    assert "Zg04_Rule3" in [row.mark.split("-")[-1] for row in rows]
    assert sum(1 for row in rows if row.mark.endswith("Zg04_Rule3")) == 1


def test_zg04_yield_rules_use_summary_rows_and_zero_amount_product_list():
    rows = run_basic_rules(
        "ZG04",
        date(2026, 5, 31),
        [
            {"projcode": "P5", "areacode": "", "clientkind": "", "moneytype": "", "dyshouyi": "4.5"},
            {"projcode": "P6", "areacode": "", "clientkind": "", "moneytype": "", "dyshouyi": "0.00000"},
            {"projcode": "P7", "areacode": "", "clientkind": "", "moneytype": "", "dyshouyi": "1.5"},
            {"projcode": "P7", "areacode": "000000", "clientkind": "1", "moneytype": "BWB", "projamtcny": "0"},
        ],
        [
            {"projcode": "P5", "areacode": "", "clientkind": "", "moneytype": "", "dyshouyi": "1.0"},
            {"projcode": "P7", "areacode": "", "clientkind": "", "moneytype": "", "dyshouyi": "1.0"},
        ],
    )

    marks = [row.mark.split("-")[-1] for row in rows]
    assert "Zg04_Rule15\uff1a\u5f53\u6708\u5e74\u5316\u6536\u76ca\u7387\u8de8\u671f\u53d8\u52a8\u8fc7\u5927\uff08\u8d85\u8fc7200%\uff09\uff0c\u9700\u6838\u5b9e" in marks
    assert "Zg04_Rule17\uff1a\u5f53\u6708\u5e74\u5316\u6536\u76ca\u7387\u4e3a0\uff0c\u9700\u6838\u5b9e" in marks
    assert "Zg04_Rule19\uff1a\u671f\u672b\u4ea7\u54c1\u91d1\u989d\u6298\u4eba\u6c11\u5e01\u4e3a0\u65f6\uff0c\u5f53\u6708\u5e74\u5316\u6536\u76ca\u7387\u6bd4\u4e0a\u671f\u6ce2\u52a8\u8d85\u8fc720%\uff0c\u9700\u6838\u5b9e" in marks


def test_zg04_remaining_legacy_rules_are_triggerable_from_database_rows():
    current_rows = [
        _zg04_row("P1", areacode="000000", clientkind="1", moneytype="BWB", projshare="100"),
        _zg04_row("P4", navamt="1.5"),
        _zg04_row("P6", navamt="2", navallamt="1"),
        _zg04_row("P7", moneytype="BWB", navamt="1"),
        _zg04_row("P7", areacode="320101", clientkind="1", moneytype="BWB", projshare="0"),
        _zg04_row("P8", areacode="000100", clientkind="1", moneytype="CNY", currraiseamt="100"),
        _zg04_row("P8", areacode="000100", clientkind="1", moneytype="BWB", currraiseamt="90"),
        _zg04_row("P9", areacode="000100", clientkind="1", moneytype="CNY", projamtcny="100"),
        _zg04_row("P11", moneytype="BWB", navamt="1"),
        _zg04_row("P11", areacode="320101", clientkind="1", moneytype="BWB", currraiseamt="200", curraiseshare="10"),
        _zg04_row("P12", areacode="320101", clientkind="1", moneytype="BWB", curcashamt="0", curcashshare="5"),
        _zg04_row("P13", moneytype="BWB", navamt="1"),
        _zg04_row("P13", areacode="320101", clientkind="1", moneytype="BWB", curcashamt="200", curcashshare="10"),
        _zg04_row("P14", moneytype="BWB", navamt="2"),
        _zg04_row("P14", areacode="320101", clientkind="1", moneytype="BWB", projshare="10000", projamtcny="1"),
        _zg04_row("P16", areacode="320101", clientkind="1", moneytype="BWB", projshare="0", projamtcny="100"),
        _zg04_row("P18", moneytype="BWB", navamt="0", navallamt="1"),
    ]
    previous_rows = [_zg04_row("P4", navamt="1"), _zg04_row("P7", moneytype="BWB", navamt="2")]

    rows = run_basic_rules(
        "ZG04",
        date(2026, 5, 31),
        current_rows,
        previous_rows,
        related_rows={
            "ZG03": [{"projcode": "P7"}],
            "ZG05": [{"projcode": "P1", "moneytype": "BWB", "datetype": "3", "c1000": "80"}],
        },
    )

    assert {
        "Zg04_Rule1",
        "Zg04_Rule4",
        "Zg04_Rule6",
        "Zg04_Rule7",
        "Zg04_Rule8",
        "Zg04_Rule9",
        "Zg04_Rule11",
        "Zg04_Rule12",
        "Zg04_Rule13",
        "Zg04_Rule14",
        "Zg04_Rule16",
        "Zg04_Rule18",
    }.issubset({_result_rule_id(row) for row in rows})


def _zg04_row(
    productcode,
    *,
    areacode="",
    clientkind="",
    moneytype="",
    currraiseamt="",
    curraiseshare="",
    curcashamt="",
    curcashshare="",
    projamt="",
    projamtcny="",
    projshare="",
    navamt="",
    navallamt="",
):
    return {
        "projcode": productcode,
        "areacode": areacode,
        "clientkind": clientkind,
        "moneytype": moneytype,
        "currraiseamt": currraiseamt,
        "curraiseshare": curraiseshare,
        "curcashamt": curcashamt,
        "curcashshare": curcashshare,
        "projamt": projamt,
        "projamtcny": projamtcny,
        "projshare": projshare,
        "navamt": navamt,
        "navallamt": navallamt,
    }


def test_zg06_selected_rules_follow_legacy_conditions_and_output_format():
    rows = run_basic_rules(
        "ZG06",
        date(2026, 5, 31),
        [
            {
                "projcode": "P1",
                "beneficialcode": "B1",
                "issuername": "出让机构1",
                "issuertype": "3",
                "issuerindustry": "J",
                "rateinfo": "2.5",
                "begdate": "2026-04-30",
            },
            {
                "projcode": "P2",
                "beneficialcode": "B2",
                "issuername": "出让机构2",
                "issuertype": "1",
                "issuerindustry": "1",
                "rateinfo": "0",
                "begdate": "2026-05-10",
            },
            {
                "projcode": "P3",
                "beneficialcode": "B3",
                "issuername": "出让机构3",
                "issuertype": "1",
                "issuerindustry": "1",
                "rateinfo": "0",
                "begdate": "2026-04-30",
            },
            {
                "projcode": "P4",
                "beneficialcode": "B4",
                "issuername": "出让机构4",
                "issuertype": "1",
                "issuerindustry": "1",
                "predate": "2099-12-31",
                "perioddate": "",
            },
            {
                "projcode": "P5",
                "beneficialcode": "B5",
                "issuername": "出让机构5",
                "issuertype": "5",
                "issuerindustry": "J",
                "kjxgcybs202502271437111": "",
                "lslybs202502271438481": "",
                "phlybs202502271440121": "",
                "ylcybs202502271441101": "",
                "szjjhxcybs202502271442061": "",
            },
        ],
        [],
    )

    marks = [row.mark.split("-")[-1] for row in rows]
    assert marks == ["Zg06_Rule3", "Zg06_Rule3", "Zg06_Rule6", "Zg06_Rule9", "Zg06_Rule14"]
    assert rows[2].value1 == "利率水平:0.00000"
    assert rows[2].value2 == ""
    assert rows[3].value2 == "转让展期到期日期:nan"
    assert rows[4].detail.endswith("_5_nan_nan_nan")
    assert rows[4].value1 == "养老产业标识:nan"


def test_zg06_remaining_legacy_rules_are_triggerable_from_database_rows():
    current_rows = [
        _zg06_row("P1", "B1", debtproj="A5100", asstetype="9"),
        _zg06_row("P2", "B2", issuertype="2", issuercode="BAD"),
        _zg06_row("P4", "B4", issuerareacode="320100"),
        _zg06_row("P5", "B5", issuertype="1", issuerentscale="1"),
        _zg06_row("P7", "B7", issuertype="4", issuerindustry="J", issuercode="123"),
        _zg06_row("P8", "B8", transferamtcny="100"),
        _zg06_row("P10", "B10", issuercode="DUP", issuername="A"),
        _zg06_row("P10", "B11", issuercode="DUP", issuername="B"),
        _zg06_row("P13", "B13", issuertype="1", kjxgcybs202502271437111="", lslybs202502271438481="", phlybs202502271440121="", ylcybs202502271441101="", szjjhxcybs202502271442061=""),
        _zg06_row("P15", "B15", taboutflg="1"),
        _zg06_row("P16", "B16", buybackflg="1"),
    ]
    previous_rows = [_zg06_row("P8", "B8", transferamtcny="80")]

    rows = run_basic_rules("ZG06", date(2026, 5, 31), current_rows, previous_rows)

    assert {
        "Zg06_Rule1",
        "Zg06_Rule2",
        "Zg06_Rule4",
        "Zg06_Rule5",
        "Zg06_Rule7",
        "Zg06_Rule8",
        "Zg06_Rule10",
        "Zg06_Rule13",
        "Zg06_Rule15",
        "Zg06_Rule16",
    }.issubset({_result_rule_id(row) for row in rows})


def test_zg06_rule8_uses_legacy_field_list_and_org_key():
    rows = run_basic_rules(
        "ZG06",
        date(2026, 5, 31),
        [
            _zg06_row("P1", "B1") | {"perioddate": "2027-01-01"},
            _zg06_row("P2", "B2") | {"jgcode": "ORG1", "transferamtcny": "100"},
        ],
        [
            _zg06_row("P1", "B1") | {"perioddate": "2026-01-01"},
            _zg06_row("P2", "B2") | {"jgcode": "ORG2", "transferamtcny": "80"},
        ],
    )

    details = [row.detail for row in rows if _result_rule_id(row) == "Zg06_Rule8"]
    assert not any("P1" in detail for detail in details)
    assert not any("P2" in detail for detail in details)


def _zg06_row(
    productcode,
    beneficialcode,
    *,
    debtproj="A1100",
    asstetype="1",
    issuername="出让机构",
    issuercode="91310000100019382F",
    issuertype="2",
    issuerindustry="C",
    issuerareacode="320101",
    issuereconomytype="1",
    issuerentscale="1",
    transferamtcny="100",
    taboutflg="2",
    buybackflg="2",
    kjxgcybs202502271437111="1",
    lslybs202502271438481="1",
    phlybs202502271440121="1",
    ylcybs202502271441101="1",
    szjjhxcybs202502271442061="1",
):
    return {
        "projcode": productcode,
        "beneficialcode": beneficialcode,
        "debtproj": debtproj,
        "asstetype": asstetype,
        "issuername": issuername,
        "issuercode": issuercode,
        "issuertype": issuertype,
        "issuerindustry": issuerindustry,
        "issuerareacode": issuerareacode,
        "issuereconomytype": issuereconomytype,
        "issuerentscale": issuerentscale,
        "transferamtcny": transferamtcny,
        "taboutflg": taboutflg,
        "buybackflg": buybackflg,
        "kjxgcybs202502271437111": kjxgcybs202502271437111,
        "lslybs202502271438481": lslybs202502271438481,
        "phlybs202502271440121": phlybs202502271440121,
        "ylcybs202502271441101": ylcybs202502271441101,
        "szjjhxcybs202502271442061": szjjhxcybs202502271442061,
    }


def test_zg06_public_info_date_rules_compare_product_dates():
    rows = run_basic_rules(
        "ZG06",
        date(2026, 5, 31),
        [
            {
                "projcode": "P11",
                "beneficialcode": "B11",
                "issuername": "出让机构11",
                "begdate": "2026-01-01",
                "predate": "2028-01-01",
            },
            {
                "projcode": "P12",
                "beneficialcode": "B12",
                "issuername": "出让机构12",
                "begdate": "2026-06-01",
                "predate": "2026-12-31",
            },
        ],
        [],
        related_rows={
            "PUBLIC_INFO": [
                {"产品代码": "P11", "产品起始日期": "2026-02-01", "产品预计终止日期": "2027-12-31"},
                {"产品代码": "P12", "产品起始日期": "2026-02-01", "产品预计终止日期": "2027-12-31"},
            ]
        },
    )

    rule_ids = {row.mark.split("-")[-1] for row in rows}

    assert {"Zg06_Rule11", "Zg06_Rule12"}.issubset(rule_ids)


def test_zg07_cross_period_rule_compares_legacy_field_list_with_formatting():
    rows = run_basic_rules(
        "ZG07",
        date(2026, 5, 31),
        [
            {
                "projcode": "P1",
                "ioucode": "IOU1",
                "loantype": "1",
                "enddate": "2027-08-30",
                "rateinfo": "3.8",
                "pactamt": "100.00",
            },
            {
                "projcode": "P2",
                "ioucode": "IOU2",
                "loantype": "4",
                "enddate": "2027-08-30",
                "rateinfo": "3.8",
            },
        ],
        [
            {
                "projcode": "P1",
                "ioucode": "IOU1",
                "loantype": "1",
                "enddate": "2026-05-30",
                "rateinfo": "8",
                "pactamt": "100",
            },
            {
                "projcode": "P2",
                "ioucode": "IOU2",
                "loantype": "4",
                "enddate": "2026-05-30",
                "rateinfo": "8",
            },
        ],
    )

    assert [row.mark for row in rows] == [
        "20260531-D1003632000013-ZG07-贷款到期日期-Zg07_Rule9",
        "20260531-D1003632000013-ZG07-利率水平-Zg07_Rule9",
    ]
    assert rows[0].detail == "产品代码_贷款借据编码:P1_IOU1"
    assert rows[0].value1 == "贷款到期日期:2027-08-30"
    assert rows[0].value2 == "贷款到期日期_上期:2026-05-30"
    assert rows[1].value1 == "利率水平:3.80000"
    assert rows[1].value2 == "利率水平_上期:8.00000"


def test_zg07_public_info_end_date_rule_checks_end_or_extension_date():
    rows = run_basic_rules(
        "ZG07",
        date(2026, 5, 31),
        [
            {
                "projcode": "P13",
                "ioucode": "IOU13",
                "debtorcode": "91310000100019382F",
                "loantype": "1",
                "enddate": "2028-01-01",
                "perioddate": "2026-06-01",
            },
            {
                "projcode": "P14",
                "ioucode": "IOU14",
                "debtorcode": "91310000100019382F",
                "loantype": "1",
                "enddate": "2026-06-01",
                "perioddate": "2028-01-01",
            },
        ],
        [],
        related_rows={
            "PUBLIC_INFO": [
                {"projcode": "P13", "projpredate": "2027-12-31"},
                {"projcode": "P14", "projpredate": "2027-12-31"},
            ]
        },
    )

    assert sum(1 for row in rows if row.mark.endswith("Zg07_Rule13")) == 2


def test_zg07_legacy_detail_rules_are_triggerable_from_database_rows():
    current_rows = [
        _zg07_row("P1", "IOU1", loanissuerareacode="320100"),
        _zg07_row("P2", "IOU2", debtortype="1", areacode="320101"),
        _zg07_row("P3", "IOU3", areacode="320100"),
        _zg07_row("P4", "IOU4", debtortype="1", debtorcode="SHORT"),
        _zg07_row("P5", "IOU5", debtortype="2", debtorcode="BAD"),
        _zg07_row("P6", "IOU6", debtortype="1", indutry="J"),
        _zg07_row("P7", "IOU7", debtortype="1", enscale="1"),
        _zg07_row("P8", "IOU8", rateinfo="0.5", grantdate="2026-05-10"),
        _zg07_row("P9", "IOU9", loanstate="FS02", perioddate=""),
        _zg07_row("P10", "IOU10", debtorcode="DUP", debtortype="2", areacode="320101"),
        _zg07_row("P11", "IOU11", debtorcode="DUP", debtortype="2", areacode="320102"),
        _zg07_row("P12", "IOU12", debtorcode=""),
        _zg07_row("P13", "IOU13", debtortype="2", iouprojtype="F021"),
        _zg07_row("P14", "IOU14", iouprojtype="X99"),
        _zg07_row("P15", "IOU15", enddate="2090-01-01"),
        _zg07_row("P16", "IOU16", loantype="4", loanissuercode="", issuercode=""),
    ]

    rows = run_basic_rules("ZG07", date(2026, 5, 31), current_rows, [])
    rule_ids = {_result_rule_id(row) for row in rows}

    assert {
        "Zg07_Rule1",
        "Zg07_Rule2",
        "Zg07_Rule3",
        "Zg07_Rule4",
        "Zg07_Rule5",
        "Zg07_Rule6",
        "Zg07_Rule7",
        "Zg07_Rule8",
        "Zg07_Rule11",
        "Zg07_Rule12",
        "Zg07_Rule14",
        "Zg07_Rule15",
        "Zg07_Rule16",
        "Zg07_Rule17",
        "Zg07_Rule18",
    }.issubset(rule_ids)


def test_zg07_rule11_uses_legacy_fs02_extension_status_and_loan_type_exception():
    rows = run_basic_rules(
        "ZG07",
        date(2026, 5, 31),
        [
            _zg07_row("P1", "IOU1", loanstate="FS03", perioddate=""),
            _zg07_row("P2", "IOU2", loanstate="FS02", perioddate=""),
            _zg07_row("P3", "IOU3", loantype="4", loanstate="FS01", perioddate="2027-01-01"),
            _zg07_row("P4", "IOU4", loanstate="", perioddate="2030-03-31") | {"ioustatus": "FS02"},
        ],
        [],
    )

    details = [row.detail for row in rows if _result_rule_id(row) == "Zg07_Rule11"]
    assert not any("P1" in detail for detail in details)
    assert any("P2" in detail for detail in details)
    assert not any("P3" in detail for detail in details)
    assert not any("P4" in detail for detail in details)


def test_zg07_rule15_uses_legacy_borrower_type_to_loan_product_mapping():
    rows = run_basic_rules(
        "ZG07",
        date(2026, 5, 31),
        [
            _zg07_row("P1", "IOU1", debtortype="1", iouprojtype="F021"),
            _zg07_row("P2", "IOU2", debtortype="3", iouprojtype="F023"),
            _zg07_row("P3", "IOU3", debtortype="2", iouprojtype="F021"),
            _zg07_row("P4", "IOU4", debtortype="1", iouprojtype="F023"),
        ],
        [],
    )

    details = [row.detail for row in rows if _result_rule_id(row) == "Zg07_Rule15"]
    assert not any("P1" in detail for detail in details)
    assert not any("P2" in detail for detail in details)
    assert any("P3" in detail for detail in details)
    assert any("P4" in detail for detail in details)


def _zg07_row(
    productcode,
    ioucode,
    *,
    loantype="1",
    loanissuercode="91310000100019382F",
    issuercode="91310000100019382F",
    loanissuerareacode="320101",
    debtortype="2",
    areacode="320101",
    debtorcode="91310000100019382F",
    indutry="C",
    economytype="1",
    enscale="1",
    iouprojtype="F02",
    grantdate="2026-05-01",
    enddate="2027-01-01",
    perioddate="",
    loanstate="FS01",
    rateinfo="2.5",
):
    return {
        "projcode": productcode,
        "ioucode": ioucode,
        "loantype": loantype,
        "loanissuercode": loanissuercode,
        "issuercode": issuercode,
        "loanissuerareacode": loanissuerareacode,
        "debtortype": debtortype,
        "areacode": areacode,
        "debtorcode": debtorcode,
        "indutry": indutry,
        "economytype": economytype,
        "enscale": enscale,
        "iouprojtype": iouprojtype,
        "grantdate": grantdate,
        "enddate": enddate,
        "perioddate": perioddate,
        "loanstate": loanstate,
        "rateinfo": rateinfo,
    }


def test_zg08_legacy_public_and_counterparty_rules_are_triggerable_from_database_rows():
    org_codes = [
        "D1003732000014",
        "D1003832000015",
        "D1003932000016",
        "E1007932000016",
        "E1008532000019",
        "E1008732000013",
        "E1008832000015",
        "E2030932000017",
    ]
    current_rows = [
        _zg08_row("P2", "A7200", "MISSING", "1", issuer="ORG999", amount="10"),
        _zg08_row("C880001", "A7200", "ORG001_PRODUCT", "1", issuer="ORG001", amount="10"),
        _zg08_row("R1", "A5200", "R2", amount="100"),
        _zg08_row("R3", "B1200", "R4", amount="100"),
        _zg08_row("S1", "A7200", "S2", amount="100"),
        _zg08_row("S3", "C1100", "S4", amount="100"),
        _zg08_row("S4", "A5200", "DUMMY", amount="100"),
        _zg08_row("P12", "A7200", "P12", "1", issuer="P12000", amount="10"),
        _zg08_row("P13", "A7200", "BAD_PRODUCT", "1", issuer="ORG001", amount="10"),
    ]
    previous_rows = [_zg08_row("OLD", "A7200", "MISSING", "1", issuer="ORG999", amount="10")]

    rows = run_basic_rules(
        "ZG08",
        date(2026, 5, 31),
        current_rows,
        previous_rows,
        related_rows={
            "ZG01": [
                {"projcode": "R1", "issuercode": "D1003632000013"},
                {"projcode": "R3", "issuercode": "D1003632000013"},
                {"projcode": "S1", "issuercode": "D1003632000013"},
                {"projcode": "S3", "issuercode": "D1003632000013"},
            ],
            "PUBLIC_INFO": [
                {"产品代码": "R1", "发行机构代码": org_codes[0]},
                {"产品代码": "R2", "发行机构代码": org_codes[1]},
                {"产品代码": "R3", "发行机构代码": org_codes[2]},
                {"产品代码": "R4", "发行机构代码": org_codes[3]},
                {"产品代码": "S1", "发行机构代码": org_codes[4]},
                {"产品代码": "S2", "发行机构代码": org_codes[5]},
                {"产品代码": "S3", "发行机构代码": org_codes[6]},
                {"产品代码": "S4", "发行机构代码": org_codes[7]},
            ]
        },
    )

    assert {
        "Zg08_Rule2",
        "Zg08_Rule3",
        "Zg08_Rule4",
        "Zg08_Rule5",
        "Zg08_Rule6",
        "Zg08_Rule7",
        "Zg08_Rule8",
        "Zg08_Rule9",
        "Zg08_Rule10",
        "Zg08_Rule11",
        "Zg08_Rule12",
        "Zg08_Rule13",
    }.issubset({_result_rule_id(row) for row in rows})


def test_zg08_rule13_reports_blank_counterparty_fields_like_legacy_program():
    rows = run_basic_rules(
        "ZG08",
        date(2026, 5, 31),
        [
            _zg08_row("P_BLANK", "A7200", "", issuer=""),
            _zg08_row("P_NO_ISSUER", "A7200", "ABCDEF0001", issuer=""),
        ],
        [],
    )

    rule13_rows = [row for row in rows if _result_rule_id(row) == "Zg08_Rule13"]

    assert len(rule13_rows) == 2
    assert any(row.value1.endswith(":") and row.value2.endswith(":") for row in rule13_rows)
    assert any(row.value1.endswith(":") and row.value2.endswith(":ABCDEF0001") for row in rule13_rows)


def test_zg08_public_info_rule_reports_invested_product_already_ended():
    rows = run_basic_rules(
        "ZG08",
        date(2026, 5, 31),
        [
            _zg08_row("P1", "A5200", "ENDED", amount="100"),
            _zg08_row("P2", "A5200", "ACTIVE", amount="100"),
        ],
        [],
        related_rows={
            "PUBLIC_INFO": [
                {"projcode": "ENDED", "actualenddate": "2026-5-1"},
                {"projcode": "ACTIVE", "actualenddate": "2026-06-01"},
            ],
        },
    )

    rule1_rows = [row for row in rows if _result_rule_id(row) == "Zg08_Rule1"]
    assert len(rule1_rows) == 1
    assert "交易对手产品代码:ENDED" == rule1_rows[0].value1
    assert "产品实际终止日期:2026-5-1" == rule1_rows[0].value2


def test_zg08_pair_rules_report_rule6_and_10_when_counterparty_is_not_in_local_zg08_rows():
    rows = run_basic_rules(
        "ZG08",
        date(2026, 5, 31),
        [
            _zg08_row("SELF", "C1100", "COUNTERPARTY", amount="100"),
        ],
        [],
        related_rows={
            "ZG01": [
                {"projcode": "SELF", "issuercode": "D1003732000014"},
            ],
            "PUBLIC_INFO": [
                {"productcode": "COUNTERPARTY", "issuerorgcode": "D1003832000015"},
            ],
        },
    )

    assert {"Zg08_Rule6", "Zg08_Rule10"}.issubset({_result_rule_id(row) for row in rows})
    reverse_rows = [row for row in rows if _result_rule_id(row) == "Zg08_Rule10"]
    assert reverse_rows[0].org_code == "D1003832000015"


def test_zg08_pair_rules_use_legacy_exact_float_change_filter():
    rows = run_basic_rules(
        "ZG08",
        date(2026, 5, 31),
        [
            _zg08_row("SELF", "C1200", "COUNTERPARTY", amount="88247155.57"),
        ],
        [],
        related_rows={
            "ZG01": [
                {"projcode": "SELF", "issuercode": "D1003732000014"},
            ],
            "PUBLIC_INFO": [
                {"productcode": "COUNTERPARTY", "issuerorgcode": "D1003832000015"},
            ],
        },
    )

    assert "Zg08_Rule6" not in {_result_rule_id(row) for row in rows}
    assert "Zg08_Rule10" not in {_result_rule_id(row) for row in rows}


def test_zg09_zg10_template_cross_checks_are_disabled_until_template_engine_is_enabled():
    zg09_rows = run_basic_rules(
        "ZG09",
        date(2026, 5, 31),
        [
            {
                "issuercode": "ORG001",
                "org_name": "Org One",
                "manager_org": "Manager One",
                "cpkj": "1",
                "fb00001": "100000",
                "fb00002": "200000",
            }
        ],
        [],
        related_rows={
            "TEMPLATE": [
                {"org_code": "ORG001", "indicator_code": "000001-A", "data_value": "20"},
                {"org_code": "ORG001", "indicator_code": "000002-A", "data_value": "25"},
            ]
        },
    )
    zg10_rows = run_basic_rules(
        "ZG10",
        date(2026, 5, 31),
        [
            {
                "issuercode": "ORG001",
                "org_name": "Org One",
                "manager_org": "Manager One",
                "cpkj": "1",
                "projtype": "1",
                "h10000": "100000",
            }
        ],
        [],
        related_rows={
            "TEMPLATE": [
                {
                    "org_code": "ORG001",
                    "product_type": "1",
                    "indicator_code": "H10000",
                    "data_value": "20",
                    "form_name": "表1-1",
                }
            ]
        },
    )

    assert zg09_rows == []
    assert zg10_rows == []


def test_zg09_zg10_template_cross_checks_use_cpkj_to_pick_template_table():
    zg09_rows = run_basic_rules(
        "ZG09",
        date(2026, 5, 31),
        [
            {
                "issuercode": "ORG001",
                "org_name": "Org One",
                "manager_org": "Manager One",
                "cpkj": "1",
                "g000a": "100000",
            },
            {
                "issuercode": "ORG001",
                "org_name": "Org One",
                "manager_org": "Manager One",
                "cpkj": "2",
                "g000a": "200000",
            },
        ],
        [],
        related_rows={
            "TEMPLATE": [
                {
                    "template_table": "balance_sheet_info",
                    "field_name": "A_g00000",
                    "field_value": "10",
                },
                {
                    "template_table": "balance_sheet_info_zcglxt",
                    "field_name": "A_g00000",
                    "field_value": "20",
                },
            ]
        },
        enable_template_check=True,
    )
    zg10_rows = run_basic_rules(
        "ZG10",
        date(2026, 5, 31),
        [
            {
                "issuercode": "ORG001",
                "org_name": "Org One",
                "manager_org": "Manager One",
                "cpkj": "1",
                "projtype": "1",
                "h15000": "100000",
            },
            {
                "issuercode": "ORG001",
                "org_name": "Org One",
                "manager_org": "Manager One",
                "cpkj": "2",
                "projtype": "1",
                "h15000": "200000",
            },
        ],
        [],
        related_rows={
            "TEMPLATE": [
                {
                    "template_table": "balance_sheet_info2",
                    "field_name": "A_h15000",
                    "field_value": "10",
                },
                {
                    "template_table": "balance_sheet_info2_zcglxt",
                    "field_name": "A_h15000",
                    "field_value": "20",
                }
            ]
        },
        enable_template_check=True,
    )

    assert zg09_rows == []
    assert zg10_rows == []


def test_zg09_zg10_template_cross_checks_report_when_matching_template_table_differs():
    zg09_rows = run_basic_rules(
        "ZG09",
        date(2026, 5, 31),
        [
            {
                "issuercode": "ORG001",
                "org_name": "Org One",
                "manager_org": "Manager One",
                "cpkj": "2",
                "g000a": "100000",
            }
        ],
        [],
        related_rows={
            "TEMPLATE": [
                {
                    "template_table": "balance_sheet_info_zcglxt",
                    "field_name": "A_g00000",
                    "field_value": "20",
                },
            ]
        },
        enable_template_check=True,
    )
    zg10_rows = run_basic_rules(
        "ZG10",
        date(2026, 5, 31),
        [
            {
                "issuercode": "ORG001",
                "org_name": "Org One",
                "manager_org": "Manager One",
                "cpkj": "2",
                "projtype": "1",
                "h15000": "100000",
            }
        ],
        [],
        related_rows={
            "TEMPLATE": [
                {
                    "template_table": "balance_sheet_info2_zcglxt",
                    "field_name": "A_h15000",
                    "field_value": "20",
                }
            ]
        },
        enable_template_check=True,
    )

    assert [row.mark for row in zg09_rows] == ["20260531-ORG001-ZG09-Zg09_Rule3"]
    assert [row.mark for row in zg10_rows] == ["20260531-ORG001-ZG10-Zg10_Rule1"]


def _zg08_row(
    productcode,
    debtproj,
    riverprojcode,
    riverprojtype="2",
    *,
    issuer="ORG001",
    amount="100",
):
    return {
        "projcode": productcode,
        "issuercode": "D1003632000013",
        "debtorproj": debtproj,
        "riverprojtype": riverprojtype,
        "riverprojcode": riverprojcode,
        "riverissuercode": issuer,
        "sharamtcny": amount,
    }


def test_zg13_financial_institution_code_rules_use_legacy_name_exceptions():
    rows = run_basic_rules(
        "ZG13",
        date(2026, 5, 31),
        [
            {
                "projcode": "P1",
                "qycode": "91310000100019382F",
                "qyname": "光大证券股份有限公司",
                "outcode": "91310000100019382F",
                "outname": "光大证券股份有限公司",
                "innercode": "I1",
                "industry": "J",
            },
            {
                "projcode": "P2",
                "qycode": "911201160587020562",
                "qyname": "大唐融资租赁有限公司",
                "outcode": "911201160587020562",
                "outname": "大唐融资租赁有限公司",
                "innercode": "I2",
                "industry": "J",
            },
            {
                "projcode": "P3",
                "qycode": "C1010511003703",
                "qyname": "中国建设银行股份有限公司",
                "outcode": "C1010511003703",
                "outname": "中国建设银行股份有限公司",
                "innercode": "I3",
                "industry": "J",
            },
        ],
        [],
    )

    assert [row.mark.split("-")[-1] for row in rows] == ["Zg13_Rule15", "Zg13_Rule16"]
    assert rows[0].detail == "产品代码_标的企业代码_其他股权投资内部编码:P1_91310000100019382F_I1"
    assert rows[0].value1 == "标的企业代码:91310000100019382F"
    assert rows[0].value2 == "标的企业名称:光大证券股份有限公司"


def test_zg13_public_info_contract_end_date_rule_matches_legacy_no_output():
    rows = run_basic_rules(
        "ZG13",
        date(2026, 5, 31),
        [
            {
                "projcode": "P15",
                "qycode": "91310000100019382F",
                "qyname": "目标企业",
                "innercode": "EQ15",
                "predate": "2028-01-01",
                "cgbl": "10",
            },
            {
                "projcode": "P16",
                "qycode": "91310000100019382F",
                "qyname": "目标企业",
                "innercode": "EQ16",
                "predate": "9999-12-31",
                "cgbl": "10",
            },
        ],
        [],
        related_rows={
            "PUBLIC_INFO": [
                {"产品代码": "P15", "产品预计终止日期": "2027-12-31", "信息类型名称": "变更资管产品基本信息", "发行机构代码": "D1003732000014"},
                {"产品代码": "P16", "产品预计终止日期": "2027-12-31", "信息类型名称": "变更资管产品基本信息", "发行机构代码": "D1003832000015"},
            ]
        },
    )

    assert not any(row.mark.endswith("Zg13_Rule9") for row in rows)


def test_zg13_legacy_rules_are_triggerable_from_database_rows():
    current_rows = [
        _zg13_row("P1", "Q1", "I1", areacode="320100"),
        _zg13_row("P2", "123456789012345679", "I2"),
        _zg13_row("P3", "", "I3"),
        _zg13_row("P4", "Q4", "I4", outcode="123456789012345679"),
        _zg13_row("P5", "Q5", "I5", outcode=""),
        _zg13_row("P6", "Q6", "I6", qygm="1"),
        _zg13_row("P6", "Q6", "I7", qygm="2"),
        _zg13_row("P7", "Q7", "I8", debtproj="A7310", qymoneycny="50"),
        _zg13_row("P8", "Q8", "I9", debtproj="A7320", qymoneycny="40"),
        _zg13_row("P9", "Q9", "I10", debtproj="A7320", predate="2028-12-31", holdrate="10"),
        _zg13_row("P10", "Q10", "I11", debtproj="A7320", industry="C"),
        _zg13_row("P11", "Q11", "I12", qyname="Changed"),
    ]
    previous_rows = [_zg13_row("P11", "Q11", "I12", qyname="Previous")]

    rows = run_basic_rules(
        "ZG13",
        date(2026, 5, 31),
        current_rows,
        previous_rows,
        related_rows={
            "ZG05": [
                {"projcode": "P7", "moneytype": "BWB", "a7310": "100"},
                {"projcode": "P8", "moneytype": "BWB", "a7320": "100"},
            ]
        },
    )

    rule_ids = {_result_rule_id(row) for row in rows}

    assert {
        "Zg13_Rule1",
        "Zg13_Rule2",
        "Zg13_Rule3",
        "Zg13_Rule4",
        "Zg13_Rule5",
        "Zg13_Rule6",
        "Zg13_Rule8",
        "Zg13_Rule10",
        "Zg13_Rule11",
        "Zg13_Rule12",
        "Zg13_Rule13",
    }.issubset(rule_ids)


def test_zg13_rule13_uses_legacy_a7320_non_financial_industry_condition():
    rows = run_basic_rules(
        "ZG13",
        date(2026, 5, 31),
        [
            _zg13_row("P1", "Q1", "I1", debtproj="A7310", industry="J"),
            _zg13_row("P2", "Q2", "I2", debtproj="A7320", industry="J"),
            _zg13_row("P3", "Q3", "I3", debtproj="A7320", industry="C"),
        ],
        [],
    )

    details = [row.detail for row in rows if _result_rule_id(row) == "Zg13_Rule13"]
    assert not any("P1" in detail for detail in details)
    assert not any("P2" in detail for detail in details)
    assert any("P3" in detail for detail in details)


def test_zg13_rule8_uses_legacy_field_list_without_target_name():
    rows = run_basic_rules(
        "ZG13",
        date(2026, 5, 31),
        [
            _zg13_row("P1", "Q1", "I1", qyname="Target A"),
            _zg13_row("P2", "Q1", "I2", qyname="Target B"),
            _zg13_row("P3", "Q2", "I3", qygm="1"),
            _zg13_row("P4", "Q2", "I4", qygm="2"),
        ],
        [],
    )

    details = [row.detail for row in rows if _result_rule_id(row) == "Zg13_Rule8"]
    assert not any("Q1" in detail for detail in details)
    assert any("Q2" in detail for detail in details)


def test_zg13_balance_rules_use_legacy_zg05_equity_fields_and_zg13_amount_aliases():
    rows = run_basic_rules(
        "ZG13",
        date(2026, 5, 31),
        [
            _zg13_row("P1", "Q1", "I1", debtproj="A7310", qymoneycny="0") | {"yecny": "100"},
            _zg13_row("P2", "Q2", "I2", debtproj="A7320", qymoneycny="0") | {"yecny": "80"},
        ],
        [],
        related_rows={
            "ZG05": [
                {"projcode": "P1", "moneytype": "BWB", "a7310": "100", "ad200": "999"},
                {"projcode": "P2", "moneytype": "BWB", "a7320": "80", "ad200": "999"},
            ]
        },
    )

    rule_ids = {_result_rule_id(row) for row in rows}
    assert "Zg13_Rule10" not in rule_ids
    assert "Zg13_Rule11" not in rule_ids


def test_zg13_rule2_and_rule5_use_legacy_social_credit_code_helper():
    rows = run_basic_rules(
        "ZG13",
        date(2026, 5, 31),
        [
            _zg13_row("P1", "SHORTCODE12345", "I1"),
            _zg13_row("P2", "123456789012345679", "I2"),
            _zg13_row("P3", "Q3", "I3", outcode="SHORTCODE12345"),
            _zg13_row("P4", "Q4", "I4", outcode="123456789012345679"),
        ],
        [],
    )

    details_by_rule = {}
    for row in rows:
        details_by_rule.setdefault(_result_rule_id(row), []).append(row.detail)
    assert not any("P1" in detail for detail in details_by_rule.get("Zg13_Rule2", []))
    assert any("P2" in detail for detail in details_by_rule.get("Zg13_Rule2", []))
    assert not any("P3" in detail for detail in details_by_rule.get("Zg13_Rule5", []))
    assert any("P4" in detail for detail in details_by_rule.get("Zg13_Rule5", []))


def _zg13_row(
    productcode,
    qycode,
    innercode,
    *,
    qyname="目标企业",
    areacode="320101",
    industry="C",
    jjcf="1",
    qygm="1",
    investtype="1",
    outcode="91310000100019382F",
    outname="出让方",
    pactccy="CNY",
    qyccy="CNY",
    holdrate="0",
    outtype="1",
    begdate="2026-01-01",
    predate="2027-01-01",
    perioddate="",
    debtproj="A7310",
    qymoneycny="100",
):
    return {
        "productcode": productcode,
        "projcode": productcode,
        "qyname": qyname,
        "areacode": areacode,
        "qycode": qycode,
        "industry": industry,
        "jjcf": jjcf,
        "qygm": qygm,
        "investtype": investtype,
        "outcode": outcode,
        "outname": outname,
        "pactccy": pactccy,
        "qyccy": qyccy,
        "holdrate": holdrate,
        "outtype": outtype,
        "begdate": begdate,
        "predate": predate,
        "perioddate": perioddate,
        "innercode": innercode,
        "debtproj": debtproj,
        "qymoneycny": qymoneycny,
    }


def _result_rule_id(row):
    match = re.search(r"Zg\d{2}_Rule\d+", f"{row.rule} {row.mark}")
    return match.group(0) if match else row.rule.split(":", 1)[0].split("：", 1)[0]
