from datetime import date

import auto_check.db_validation.engine as engine_module
from auto_check.db_validation.engine import DbValidationEngine
from auto_check.db_validation.metadata import TableFieldCatalog


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
            }
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
            }
        ),
        output_dir=tmp_path,
    )

    engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG01"])

    row = captured["rows"][0]
    assert row["产品代码"] == "P1"
    assert row["产品名称"] == "Product One"


def test_engine_reuses_dependency_table_when_later_selected(tmp_path, monkeypatch):
    fetched_tables = []

    def fake_fetch_table(self, table_name):
        fetched_tables.append(table_name)
        return []

    monkeypatch.setattr(engine_module.ValidationTableReader, "fetch_table", fake_fetch_table)
    monkeypatch.setattr(engine_module, "run_basic_rules", lambda *args, **kwargs: [])

    engine = DbValidationEngine(data_client=FakeClient({}), output_dir=tmp_path)

    engine.run(report_date=date(2026, 5, 31), selected_tables=["ZG04", "ZG05"])

    assert fetched_tables.count("zgxgzh_projdebt_zg05_2024") == 1


def test_engine_reads_db_template_tables_when_template_check_enabled(tmp_path, monkeypatch):
    captured = {}

    def fake_run_basic_rules(
        zg_code,
        report_date,
        current_rows,
        previous_rows,
        related_rows=None,
        enable_template_check=False,
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
    metadata_sql, metadata_params = metadata_client.calls[0]
    assert "sys_manage_id IN (%s)" in metadata_sql
    assert "classification_id IN (%s)" in metadata_sql
    assert metadata_params == ("TEMPLATE_SYS", "TEMPLATE_CLASS")
    assert all("balance_sheet_info_zcglxt" in sql for sql, _ in template_client.calls)
