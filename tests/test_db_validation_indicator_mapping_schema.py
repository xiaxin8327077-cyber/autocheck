from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_indicator_mapping_schema_and_zg09_defaults_are_initialized():
    sql = (ROOT / "sql/app_storage/mysql/017_db_validation_mapping.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS db_validation_cross_table_mappings" in sql
    for column in (
        "automatic_detail_field_name", "override_detail_field_name", "effective_detail_field_name",
        "automatic_template_table_name", "override_template_table_name", "effective_template_table_name",
        "automatic_template_field_name", "override_template_field_name", "effective_template_field_name",
    ):
        assert column in sql
    assert "('ZG09:1:fb00001', 'ZG09', '1', 'fb00001'" in sql
    assert "'balance_sheet_info', NULL, 'balance_sheet_info', 'f1'" in sql
    assert "('ZG09:2:fb00002', 'ZG09', '2', 'fb00002'" in sql
    assert "'balance_sheet_info_zcglxt', NULL, 'balance_sheet_info_zcglxt', 'f2'" in sql
    assert "db_validation_mapping_indicators" not in sql
