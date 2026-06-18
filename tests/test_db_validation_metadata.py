from auto_check.db_validation.metadata import FieldMetadataLoader


PRODUCT_CODE = "\u4ea7\u54c1\u4ee3\u7801"
PRODUCT_NAME = "\u4ea7\u54c1\u540d\u79f0"
UNKNOWN_FIELD = "\u672a\u5339\u914d\u5b57\u6bb5"
MISSING_FIELD = "\u4e0d\u5b58\u5728"


class FakeConfig:
    db_type = "postgresql"
    schema = "meta"


class FakeClient:
    def __init__(self):
        self.config = FakeConfig()
        self.calls = []

    def fetch_all(self, sql, params=()):
        self.calls.append((sql, params))
        if "xt_reg_table_baseinfo" in sql or "baseinfo_custom" in sql:
            return [{"id": "t1", "table_name_en": "zgxgzh_baseinfo_zg01_26"}]
        if "xt_reg_table_field_info" in sql or "field_info_custom" in sql:
            return [
                {"table_id": "t1", "field_propert": "projcode", "field_name": PRODUCT_CODE, "sort": "1"},
                {"table_id": "t1", "field_propert": "projname", "field_name": PRODUCT_NAME, "sort": "2"},
                {"table_id": "missing", "field_propert": "unknown", "field_name": UNKNOWN_FIELD, "sort": "3"},
            ]
        return []


def test_metadata_loader_maps_chinese_names_to_english_fields():
    loader = FieldMetadataLoader(FakeClient())

    catalog = loader.load()

    assert catalog.field_for("zgxgzh_baseinfo_zg01_26", PRODUCT_CODE) == "projcode"
    assert catalog.field_for("zgxgzh_baseinfo_zg01_26", PRODUCT_NAME) == "projname"
    assert catalog.unmapped_field_count == 0


def test_metadata_loader_ignores_fields_outside_selected_detail_tables():
    loader = FieldMetadataLoader(FakeClient(), sys_manage_id="DETAIL_SYS", classification_id="DETAIL_CLASS")

    catalog = loader.load()

    assert catalog.field_for("zgxgzh_baseinfo_zg01_26", PRODUCT_CODE) == "projcode"
    assert catalog.field_for("zgxgzh_baseinfo_zg01_26", PRODUCT_NAME) == "projname"
    assert set(catalog.by_table) == {"zgxgzh_baseinfo_zg01_26"}
    assert catalog.unmapped_field_count == 0


def test_metadata_loader_reports_missing_field():
    loader = FieldMetadataLoader(FakeClient())
    catalog = loader.load()

    try:
        catalog.field_for("zgxgzh_baseinfo_zg01_26", MISSING_FIELD)
    except KeyError as exc:
        assert f"zgxgzh_baseinfo_zg01_26.{MISSING_FIELD}" in str(exc)
    else:
        raise AssertionError("expected missing field KeyError")


def test_metadata_loader_filters_baseinfo_by_semicolon_separated_ids():
    client = FakeClient()
    loader = FieldMetadataLoader(client, sys_manage_id="SYS1;SYS2", classification_id="CLASS1;CLASS2")

    loader.load()

    baseinfo_sql, params = client.calls[0]
    assert '"meta"."xt_reg_table_baseinfo"' in baseinfo_sql
    assert "sys_manage_id IN (%s, %s)" in baseinfo_sql
    assert "classification_id IN (%s, %s)" in baseinfo_sql
    assert params == ("SYS1", "SYS2", "CLASS1", "CLASS2")


def test_metadata_loader_filters_field_info_to_selected_baseinfo_ids():
    client = FakeClient()
    loader = FieldMetadataLoader(client)

    loader.load()

    field_sql, params = client.calls[1]
    assert '"meta"."xt_reg_table_field_info"' in field_sql
    assert "table_id IN (%s)" in field_sql
    assert params == ("t1",)


def test_metadata_loader_uses_configured_table_names():
    client = FakeClient()
    loader = FieldMetadataLoader(
        client,
        baseinfo_table="baseinfo_custom",
        field_info_table="field_info_custom",
    )

    loader.load()

    assert '"meta"."baseinfo_custom"' in client.calls[0][0]
    assert '"meta"."field_info_custom"' in client.calls[1][0]
