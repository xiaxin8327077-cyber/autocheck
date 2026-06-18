from datetime import date

from auto_check.db_validation.rules.basic import run_basic_rules


def test_zg12_all_legacy_rules_are_triggerable_from_database_rows():
    current_rows = [
        _zg12_row("P1", "D1", "I1", jkrtype="1", areacode="320100"),
        _zg12_row("P2", "", "I2"),
        _zg12_row("P3", "SHORT", "I3", jkrtype="1"),
        _zg12_row("P4", "BAD", "I4", jkrtype="2"),
        _zg12_row("P5", "D5", "I5", jkrtype="1", industry="J"),
        _zg12_row("P6", "D6", "I6", jkrtype="1", qygm="1"),
        _zg12_row("P7", "D7", "I7", lsp="0.5", startdate="2026-05-10"),
        _zg12_row("P8", "D8", "I8", jkrtype="2"),
        _zg12_row("P9", "D9", "I9", djcode="BAD"),
        _zg12_row("P10", "D10", "I10", predate="2090-01-01"),
        _zg12_row("P11", "D11", "I11", areacode="320101"),
        _zg12_row("P12", "D11", "I12", areacode="320102"),
        _zg12_row("P13", "D13", "I13", zqtype="1", djplace="2"),
        _zg12_row("P14", "D14", "I14", zqmoneycny="50"),
        _zg12_row("P15", "D15", "I15", djplace="4", djcode="BAD"),
        _zg12_row("P16", "D16", "I16", danbaotype="Z"),
        _zg12_row("P17", "D17", "I17", predate="2027-01-01"),
    ]
    previous_rows = [_zg12_row("P8", "D8", "I8", jkrtype="3")]

    rows = run_basic_rules(
        "ZG12",
        date(2026, 5, 31),
        current_rows,
        previous_rows,
        related_rows={
            "PUBLIC_INFO": [{"projcode": "P17", "projpredate": "2026-12-31"}],
            "ZG05": [{"projcode": "P14", "moneytype": "BWB", "ad200": "100"}],
        },
    )

    rule_ids = {_result_rule_id(row) for row in rows}

    assert {
        "Zg12_Rule1",
        "Zg12_Rule2",
        "Zg12_Rule3",
        "Zg12_Rule4",
        "Zg12_Rule5",
        "Zg12_Rule6",
        "Zg12_Rule7",
        "Zg12_Rule8",
        "Zg12_Rule9",
        "Zg12_Rule10",
        "Zg12_Rule11",
        "Zg12_Rule12",
        "Zg12_Rule13",
        "Zg12_Rule14",
        "Zg12_Rule16",
        "Zg12_Rule17",
        "Zg12_Rule18",
    }.issubset(rule_ids)


def _zg12_row(
    productcode,
    jkrid,
    incode,
    *,
    jkrtype="2",
    areacode="",
    industry="",
    jjcf="",
    qygm="",
    sjtx="",
    startdate="2026-04-01",
    predate="2027-01-01",
    newdate="",
    lsp="2.5",
    danbaotype="A",
    htbz="CNY",
    htmoney="100",
    htmoneycny="100",
    zqbz="CNY",
    zqmoneycny="100",
    zqtype="2",
    djplace="2",
    djcode="91310000100019382F",
):
    return {
        "productcode": productcode,
        "projcode": productcode,
        "jkrtype": jkrtype,
        "areacode": areacode,
        "jkrid": jkrid,
        "industry": industry,
        "jjcf": jjcf,
        "qygm": qygm,
        "incode": incode,
        "sjtx": sjtx,
        "startdate": startdate,
        "predate": predate,
        "newdate": newdate,
        "lsp": lsp,
        "danbaotype": danbaotype,
        "htbz": htbz,
        "htmoney": htmoney,
        "htmoneycny": htmoneycny,
        "zqbz": zqbz,
        "zqmoneycny": zqmoneycny,
        "zqtype": zqtype,
        "djplace": djplace,
        "djcode": djcode,
    }


def _result_rule_id(row):
    value = row.rule.split(":", 1)[0].split("：", 1)[0]
    if value.startswith("Zg12_Rule9"):
        return "Zg12_Rule9"
    return value
