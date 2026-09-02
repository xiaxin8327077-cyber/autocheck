from datetime import date

import auto_check.db_validation.engine as engine_module
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
            return [{"id": "t1", "table_name_en": "zgxgzh_baseinfo_zg01_26"}]
        if "xt_reg_table_field_info" in sql:
            return [
                {"table_id": "t1", "field_propert": "projcode", "field_name": "产品代码", "sort": "1"},
                {"table_id": "t1", "field_propert": "projname", "field_name": "产品名称", "sort": "2"},
                {"table_id": "t1", "field_propert": "issuername", "field_name": "发行机构名称", "sort": "3"},
            ]
        for table, rows in self.rows_by_table.items():
            if table in sql:
                return rows
        return []


class FakeTemplateMetadataClient(FakeClient):
    def fetch_all(self, sql, params=()):
        self.calls.append((sql, params))
        if "xt_reg_table_baseinfo" in sql:
            return [{"table_name_en": "balance_sheet_info_zcglxt"}]
        return []


def test_engine_generates_empty_excel_when_no_rows(tmp_path):
    client = FakeClient({})
    engine = DbValidationEngine(
        data_client=client,
        metadata_client=client,
        field_catalog=TableFieldCatalog({}, table_mappings=DETAIL_TABLE_MAPPINGS),
        output_dir=tmp_path,
    )

    result = engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG01"])

    assert result.report_date == "2026-05-31"
    assert result.error_count == 0
    assert result.excel_path.exists()


def test_engine_runs_zg01_product_name_rule(tmp_path):
    client = FakeClient(
        {
            "zgxgzh_baseinfo_zg01_26": [
                {
                    "projcode": "D100362600001",
                    "projname": "A?",
                    "issuername": "江苏省国际信托有限责任公司",
                }
            ],
        }
    )
    engine = DbValidationEngine(
        data_client=client,
        metadata_client=client,
        field_catalog=TableFieldCatalog(
            {
                "zgxgzh_baseinfo_zg01_26": {
                    "产品代码": "projcode",
                    "产品名称": "projname",
                }
            },
            table_mappings=DETAIL_TABLE_MAPPINGS,
        ),
        output_dir=tmp_path,
    )

    result = engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG01"])

    assert result.error_count == 1
    assert result.rows[0].mark.endswith("ZG01-Zg01_Rule6")
    assert "产品名称长度小于等于5个字" in result.rows[0].rule


def test_engine_adds_legacy_chinese_field_aliases_from_metadata(tmp_path, monkeypatch):
    captured = {}

    def fake_run_basic_rules(
        zg_code,
        report_date,
        current_rows,
        previous_rows,
        related_rows=None,
        enable_template_check=False,
        **kwargs,
    ):
        captured["rows"] = current_rows
        return []

    monkeypatch.setattr(engine_module, "run_basic_rules", fake_run_basic_rules)
    client = FakeClient(
        {
            "zgxgzh_baseinfo_zg01_26": [
                {
                    "projcode": "P1",
                    "projname": "Product One",
                }
            ],
        }
    )
    engine = DbValidationEngine(
        data_client=client,
        metadata_client=client,
        field_catalog=TableFieldCatalog(
            {
                "zgxgzh_baseinfo_zg01_26": {
                    "产品代码": "projcode",
                    "产品名称": "projname",
                }
            },
            table_mappings=DETAIL_TABLE_MAPPINGS,
        ),
        output_dir=tmp_path,
    )

    engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG01"])

    row = captured["rows"][0]
    assert row["产品代码"] == "P1"
    assert row["产品名称"] == "Product One"


def test_engine_uses_runtime_zg07_loan_balance_mapping_for_zg05_rule3(tmp_path):
    zg05_table = DETAIL_TABLE_MAPPINGS[("detail", "ZG05", "")]
    zg07_table = DETAIL_TABLE_MAPPINGS[("detail", "ZG07", "")]
    runtime_balance_field = "runtime_loan_balance_column"
    client = FakeClient(
        {
            zg05_table: [{
                "projcode": "P1",
                "moneytype": "BWB",
                "datetype": "3",
                "a5100": "100",
            }],
            zg07_table: [{
                "projcode": "P1",
                runtime_balance_field: "80",
            }],
        }
    )
    catalog = TableFieldCatalog(
        {
            zg05_table: {
                "产品代码": "projcode",
                "币种": "moneytype",
                "数据类型": "datetype",
                "A5100_除回购和拆借外贷款": "a5100",
            },
            zg07_table: {
                "产品代码": "projcode",
                "贷款余额折人民币": runtime_balance_field,
            },
        },
        table_mappings=DETAIL_TABLE_MAPPINGS,
    )
    engine = DbValidationEngine(data_client=client, field_catalog=catalog, output_dir=tmp_path)

    result = engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG05"])

    row = next(item for item in result.rows if item.mark.endswith("Zg05_Rule3"))
    assert row.value1 == "ZG07_贷款余额折人民币:80.0"
    assert row.value2 == "差值（G05减G07）:20.0"


def test_engine_reuses_dependency_table_when_later_selected(tmp_path, monkeypatch):
    fetched_tables = []

    def fake_fetch_table(self, table_name, decrypt_column=""):
        fetched_tables.append(table_name)
        return []

    monkeypatch.setattr(engine_module.ValidationTableReader, "fetch_table", fake_fetch_table)
    monkeypatch.setattr(engine_module, "run_basic_rules", lambda *args, **kwargs: [])

    engine = DbValidationEngine(data_client=FakeClient({}), field_catalog=TableFieldCatalog({}, table_mappings=DETAIL_TABLE_MAPPINGS), output_dir=tmp_path)

    engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG04", "ZG05"])

    assert fetched_tables.count("zgxgzh_projdebt_zg05_2024") == 1


def test_engine_requests_zg07_borrower_code_decryption_from_mapping(tmp_path):
    client = FakeClient({"zg07_detail_new": []})
    engine = DbValidationEngine(
        data_client=client,
        field_catalog=TableFieldCatalog(
            {"zg07_detail_new": {"借款人代码": "jkrcode", "产品代码": "projcode"}},
            table_mappings={("detail", "ZG07", ""): "zg07_detail_new"},
        ),
        output_dir=tmp_path,
    )

    engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG07"])

    decrypt_calls = [sql for sql, _ in client.calls if "public.decrypt" in sql]
    assert len(decrypt_calls) == 2
    assert all('decode(convert_from("jkrcode", \'UTF8\'), \'hex\')' in sql for sql in decrypt_calls)
    assert any("zg07_detail_new_2026_04" in sql for sql in decrypt_calls)


def test_engine_reads_db_template_tables_when_template_check_enabled(tmp_path, monkeypatch):
    captured = {}

    def fake_run_basic_rules(
        zg_code,
        report_date,
        current_rows,
        previous_rows,
        related_rows=None,
        enable_template_check=False,
        **kwargs,
    ):
        captured[zg_code] = {
            "related_rows": related_rows or {},
            "enable_template_check": enable_template_check,
        }
        return []

    monkeypatch.setattr(engine_module, "run_basic_rules", fake_run_basic_rules)
    data_client = FakeClient({"zgxgzh_debtordate_zg09": [{"issuercode": "ORG001", "cpkj": "1"}]})
    template_client = FakeClient(
        {
            "balance_sheet_info_zcglxt": [
                {"field_name": "A_g00000", "field_value": "20"},
            ]
        }
    )
    metadata_client = FakeTemplateMetadataClient({})
    engine = DbValidationEngine(
        data_client=data_client,
        metadata_client=metadata_client,
        template_client=template_client,
        field_catalog=TableFieldCatalog(
            {},
            table_mappings={**DETAIL_TABLE_MAPPINGS,
                ("detail", "ZG09", ""): "zgxgzh_debtordate_zg09",
                ("template", "ZG09", "2"): "balance_sheet_info_zcglxt",
            },
        ),
        template_sys_manage_id="TEMPLATE_SYS",
        template_classification_id="TEMPLATE_CLASS",
        output_dir=tmp_path,
    )

    engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG09"], enable_template_check=True)

    assert captured["ZG09"]["enable_template_check"] is True
    assert captured["ZG09"]["related_rows"]["TEMPLATE"] == [
        {
            "template_table": "balance_sheet_info_zcglxt",
            "field_name": "A_g00000",
            "field_value": "20",
        }
    ]
    assert metadata_client.calls == []
    assert all("balance_sheet_info_zcglxt" in sql for sql, _ in template_client.calls)
