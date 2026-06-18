from datetime import date

from auto_check.db_validation.engine import DbValidationEngine


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
