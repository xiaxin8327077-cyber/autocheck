from datetime import date

import pytest

from auto_check.db_validation.engine import DbValidationEngine
from auto_check.db_validation.metadata import TableFieldCatalog


DETAIL_TABLE_MAPPINGS = {
    ("detail", "ZG01", ""): "zgxgzh_baseinfo_zg01_26",
    ("detail", "ZG02", ""): "zgxgzh_begraiseinfo_zg02_26",
    ("detail", "ZG03", ""): "zgxgzh_projendinfo_zg03_26",
    ("detail", "ZG04", ""): "zgxgzh_projholdinfo_zg04",
    ("detail", "ZG05", ""): "zgxgzh_projdebt_zg05_2024",
    ("detail", "ZG06", ""): "zgxgzh_beneficial_zg06",
    ("detail", "ZG07", ""): "zgxgzh_ioudetail_zg07",
    ("detail", "ZG08", ""): "zgxgzh_spvdetail_zg08",
    ("detail", "ZG09", ""): "zgxgzh_debtordate_zg09",
    ("detail", "ZG10", ""): "zgxgzh_surecinfo_zg10",
    ("detail", "ZG11", ""): "zgxgzh_industinfo_zg11",
    ("detail", "ZG12", ""): "zgzgzh_zg12",
    ("detail", "ZG13", ""): "zgzgzh_zg13",
    ("public_info", "PUBLIC_INFO", ""): "public_information_rh",
}

ZG12_FIELD_MAP = {
    "产品代码": "productcode",
    "借款人代码": "jkrid",
    "借款人类型": "jkrtype",
    "地区代码": "areacode",
    "行业信息": "industry",
    "企业出资人经济成分": "jjcf",
    "企业规模": "qygm",
    "内部编码": "incode",
    "除资产收益权外其他债权起始日期": "startdate",
    "除资产收益权外其他债权预计到期日期": "predate",
    "利率水平": "lsp",
    "担保方式": "danbaotype",
    "债权类型": "zqtype",
    "登记交易场所": "djplace",
    "登记交易场所代码": "djcode",
    "除资产收益权外其他债权余额折人民币": "zqmoneycny",
}

PUBLIC_INFO_FIELD_MAP = {
    "产品代码": "projcode",
    "产品预计终止日期": "projpredate",
}


class FakeConfig:
    db_type = "postgresql"
    schema = "dws"


class FakeClient:
    def __init__(self, rows_by_table):
        self.rows_by_table = rows_by_table
        self.config = FakeConfig()
        self.calls = []

    def fetch_all(self, sql, params=()):
        self.calls.append((sql, params))
        if "xt_reg_table_baseinfo" in sql:
            return [{"id": "t1", "table_name_en": "zgzgzh_zg12"}]
        if "xt_reg_table_field_info" in sql:
            return []
        for table, rows in self.rows_by_table.items():
            if table in sql:
                return rows
        return []


def test_engine_reads_public_information_only_when_enabled(tmp_path):
    data_client = FakeClient(
        {
            "zgzgzh_zg12": [_zg12_row("P17", "91310000100019382F", "I17", predate="2027-01-01")],
        }
    )
    public_client = FakeClient(
        {
            "public_information_rh": [{"projcode": "P17", "projpredate": "2026-12-31"}],
        }
    )
    engine = DbValidationEngine(
        data_client=data_client,
        metadata_client=data_client,
        public_info_client=public_client,
        field_catalog=TableFieldCatalog(
            {
                "zgzgzh_zg12": ZG12_FIELD_MAP,
                "public_information_rh": PUBLIC_INFO_FIELD_MAP,
            },
            table_mappings=DETAIL_TABLE_MAPPINGS,
        ),
        output_dir=tmp_path,
    )

    disabled = engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG12"], enable_public_info_check=False)
    disabled_public_calls = list(public_client.calls)
    enabled = engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG12"], enable_public_info_check=True)

    assert not any("public_information_rh" in sql for sql, _ in disabled_public_calls)
    assert any("public_information_rh" in sql for sql, _ in public_client.calls)
    assert any(row.rule.startswith("Zg12_Rule13") for row in enabled.rows)
    assert "公开信息校验（是）" in enabled.excel_path.name
    assert "公开信息校验（否）" in disabled.excel_path.name


def test_engine_blocks_public_info_check_when_mapping_missing(tmp_path):
    data_client = FakeClient({"zgzgzh_zg12": []})
    public_client = FakeClient({})
    engine = DbValidationEngine(
        data_client=data_client,
        public_info_client=public_client,
        field_catalog=TableFieldCatalog({}, table_mappings={("detail", "ZG12", ""): "zgzgzh_zg12"}),
        output_dir=tmp_path,
    )

    with pytest.raises(RuntimeError, match="公开信息物理表映射缺失"):
        engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG12"], enable_public_info_check=True)


def _zg12_row(
    productcode,
    jkrid,
    incode,
    *,
    predate="2027-01-01",
):
    return {
        "productcode": productcode,
        "projcode": productcode,
        "jkrtype": "2",
        "areacode": "320101",
        "jkrid": jkrid,
        "industry": "C",
        "jjcf": "1",
        "qygm": "1",
        "incode": incode,
        "sjtx": "A",
        "startdate": "2026-04-01",
        "predate": predate,
        "newdate": "",
        "lsp": "2.5",
        "danbaotype": "A",
        "htbz": "CNY",
        "htmoney": "100",
        "htmoneycny": "100",
        "zqbz": "CNY",
        "zqmoneycny": "100",
        "zqtype": "2",
        "djplace": "2",
        "djcode": "91310000100019382F",
    }
