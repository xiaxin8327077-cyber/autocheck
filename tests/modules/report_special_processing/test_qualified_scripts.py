"""Dialect identifier quoting and frontend/backend qualification parity."""
from types import SimpleNamespace

import pytest

from auto_check.modules.report_special_processing.metadata import DatasourceMetadataService
from auto_check.modules.report_special_processing.sql_builder import generate_script
from auto_check.modules.report_special_processing.structured_content import parse_structured_content
from tests.modules.report_special_processing.test_script_preview_frontend import run_preview
from tests.modules.report_special_processing.test_service import ACTOR, FakeMetadata, MultiDictionary, _payload, _service, _structured_payload


@pytest.mark.parametrize("db_type,scope,quote", [
    ("postgresql", "dws", '"'),
    ("postgresql", 'reg-report-analysis', '"'),
    ("postgresql", '1104report', '"'),
    ("postgresql", 'Mixed Case.\"scope', '"'),
    ("mysql", '1104report', '`'),
    ("mysql", 'reg-report-analysis', '`'),
    ("mysql", 'Mixed Case.`scope', '`'),
])
def test_qualified_identifiers_preserve_names_and_frontend_backend_parity(tmp_path, db_type, scope, quote):
    payload = _structured_payload(datasource_type=db_type)
    table = payload["tables"][0]
    table.update(schema=scope, table_name='1104.Order-' + quote + 'name',
                 limit_report_period=True, report_period_field='Date Field', report_period_field_source='MANUAL')
    table["fields"][0]["column_name"] = 'select' + quote + 'Field'
    table["conditions"][0]["column_name"] = 'Condition.Name'
    content = parse_structured_content(payload)
    script = generate_script(content, report_period="2026-10-01")
    quoted = lambda name: quote + name.replace(quote, quote * 2) + quote
    assert f'UPDATE {quoted(scope)}.{quoted(table["table_name"])}\n' in script
    assert f'SET {quoted(table["fields"][0]["column_name"])}' in script
    assert f'WHERE {quoted("Date Field")} = ' in script
    assert f'{quoted("Condition.Name")} IN ' in script
    assert run_preview(tmp_path, content.to_dict(), report_period="2026-10-01") == script


@pytest.mark.parametrize("table_name,expected", [
    ("dws.ta_pact_detail_dws", '"dws"."ta_pact_detail_dws"'),
    ('"reg-report-analysis"."Order"', '"reg-report-analysis"."Order"'),
    ('"a.b"."table""name"', '"a.b"."table""name"'),
])
def test_legacy_qualified_table_without_snapshot_is_not_prefixed_twice(tmp_path, table_name, expected):
    payload = _structured_payload()
    payload["tables"][0].update(schema="", table_name=table_name)
    content = parse_structured_content(payload)
    script = generate_script(content)
    assert f"UPDATE {expected}\n" in script
    assert run_preview(tmp_path, content.to_dict()) == script


def test_missing_metadata_does_not_guess_database_from_display_name(tmp_path):
    payload = _structured_payload()
    payload["tables"][0].update(schema="", datasource_name="展示名绝非数据库")
    content = parse_structured_content(payload)
    script = generate_script(content)
    assert 'UPDATE "t_customer"\n' in script
    assert run_preview(tmp_path, content.to_dict()) == script


@pytest.mark.parametrize("db_type,scope,quote", [("postgresql", "reg-report-analysis", '"'), ("mysql", "1104report", '`')])
def test_generate_api_uses_config_scope_and_pins_real_dialect(db_type, scope, quote):
    config = SimpleNamespace(db_type=db_type, schema=scope if db_type == "postgresql" else "wrong_schema",
                             database=scope if db_type == "mysql" else "wrong_database")
    service = _service(metadata=FakeMetadata({"ds1": SimpleNamespace(name="展示名", config=config)}))
    payload = _structured_payload()
    payload["tables"][0]["schema"] = ""
    script = service.generate_script({"structured_content": payload}, ACTOR)["script"]
    assert f"UPDATE {quote}{scope}{quote}.{quote}t_customer{quote}\n" in script


def test_mysql_metadata_scope_uses_database_even_when_schema_is_set():
    assert DatasourceMetadataService._scope(SimpleNamespace(schema="wrong", database="1104report"), "mysql") == "1104report"


def test_manual_and_legacy_scripts_are_saved_without_rewriting():
    service = _service(dictionary=MultiDictionary(), metadata=FakeMetadata())
    manual = 'UPDATE t_customer SET customer_status=42; -- handwritten'
    record = service.create(_payload(structured_content=_structured_payload(), processing_script=manual,
                                     processing_script_mode="MANUAL"), ACTOR, request_id="manual-quoted")
    assert record["processing_script"] == manual
    legacy = service.create(_payload(processing_script=manual), ACTOR, request_id="legacy-quoted")
    assert legacy["processing_script"] == manual


def test_deleted_datasource_generate_rejects_instead_of_guessing_scope():
    from auto_check.modules.report_special_processing.contracts import ValidationError
    service = _service(metadata=FakeMetadata({}))
    with pytest.raises(ValidationError) as exc:
        service.generate_script({"structured_content": _structured_payload()}, ACTOR)
    assert "datasource_id" in exc.value.fields


@pytest.mark.parametrize("db_type,scope", [("postgresql", "DWS"), ("mysql", "1104report")])
def test_configuration_fallback_frontend_backend_parity(tmp_path, db_type, scope):
    payload = _structured_payload(datasource_type=db_type)
    payload["tables"][0]["schema"] = ""
    content = parse_structured_content(payload)
    datasources = {"ds1": {"db_type": db_type, "schema": scope, "database": scope}}
    script = generate_script(content, datasources=datasources)
    assert run_preview(tmp_path, content.to_dict(), datasources=datasources) == script


def test_mysql_current_database_overrides_stale_schema_snapshot(tmp_path):
    payload = _structured_payload(datasource_type="mysql")
    payload["tables"][0]["schema"] = "wrong_schema"
    content = parse_structured_content(payload)
    datasources = {"ds1": {"db_type": "mysql", "schema": "wrong_schema", "database": "1104report"}}
    script = generate_script(content, datasources=datasources)
    assert "UPDATE `1104report`.`t_customer`" in script
    assert run_preview(tmp_path, content.to_dict(), datasources=datasources) == script


@pytest.mark.parametrize("invalid", ["x\x00y", "x\ny", "\nt_customer", "t_customer\n", "x｜y", "x；y"])
def test_special_identifiers_still_reject_controls_and_compatibility_delimiters(invalid):
    from auto_check.modules.report_special_processing.structured_content import StructuredContentError
    payload = _structured_payload()
    payload["tables"][0]["table_name"] = invalid
    with pytest.raises(StructuredContentError):
        parse_structured_content(payload)


@pytest.mark.parametrize("invalid", ["s\x00x", "s\nx", "\nschema", "schema\n"])
def test_schema_snapshot_rejects_raw_control_characters(invalid):
    from auto_check.modules.report_special_processing.structured_content import StructuredContentError
    payload = _structured_payload()
    payload["tables"][0]["schema"] = invalid
    with pytest.raises(StructuredContentError):
        parse_structured_content(payload)


def test_physical_identifier_whitespace_is_preserved_and_schema_delimiters_are_atomic(tmp_path):
    payload = _structured_payload()
    table = payload["tables"][0]
    table.update(schema="Schema｜；.Space", table_name=" Table ", report_period_field=" Date ",
                 limit_report_period=True, report_period_field_source="MANUAL")
    table["fields"][0]["column_name"] = " Select "
    table["conditions"][0]["column_name"] = " Condition "
    content = parse_structured_content(payload)
    assert content.tables[0].table_name == " Table "
    assert content.tables[0].fields[0].column_name == " Select "
    script = generate_script(content, report_period="2026-10-01")
    assert 'UPDATE "Schema｜；.Space"." Table "' in script
    assert run_preview(tmp_path, content.to_dict(), report_period="2026-10-01") == script


def test_column_metadata_service_preserves_raw_physical_table_name():
    metadata = FakeMetadata()
    service = _service(metadata=metadata)
    service.list_datasource_columns("ds1", " Table ", {})
    assert metadata.column_calls[0][1] == " Table "


def test_metadata_adapter_preserves_raw_table_name_for_parameter_binding(monkeypatch):
    metadata = DatasourceMetadataService(None)
    monkeypatch.setattr(metadata, "_query", lambda datasource_id, **kwargs: kwargs["sql_by_dialect"][1])
    assert metadata.list_columns("ds1", " Table ") == " Table "


@pytest.mark.parametrize("dialect", ["pg", "mysql"])
def test_metadata_scope_preserves_configured_physical_whitespace(dialect):
    assert DatasourceMetadataService._scope(SimpleNamespace(schema=" Schema ", database=" Database "), dialect) == (
        " Database " if dialect == "mysql" else " Schema "
    )
