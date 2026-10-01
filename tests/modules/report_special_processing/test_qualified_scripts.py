"""Dialect identifier quoting and frontend/backend qualification parity."""
from types import SimpleNamespace

import pytest
import re
from pathlib import Path

from sqlalchemy.dialects.mysql.base import RESERVED_WORDS_MYSQL
from sqlalchemy.dialects.postgresql.base import RESERVED_WORDS

from auto_check.modules.report_special_processing.metadata import DatasourceMetadataService
from auto_check.modules.report_special_processing.sql_builder import generate_script
from auto_check.modules.report_special_processing.structured_content import parse_structured_content
from tests.modules.report_special_processing.test_script_preview_frontend import run_preview
from tests.modules.report_special_processing.test_service import ACTOR, FakeMetadata, MultiDictionary, _payload, _service, _structured_payload


ROOT = Path(__file__).resolve().parents[3]


def _javascript_keyword_words(source: str, constant: str) -> set[str]:
    match = re.search(rf"const {constant}\s*=\s*new Set\(\[([\s\S]*?)\]\);", source)
    assert match, f"missing JavaScript keyword snapshot {constant}"
    return set(re.findall(r"['\"]([a-z][a-z0-9_]*)['\"]", match.group(1)))


@pytest.mark.parametrize("db_type,scope,quote,expected_scope", [
    ("postgresql", "dws", '"', "dws"),
    ("postgresql", 'reg-report-analysis', '"', '"reg-report-analysis"'),
    ("postgresql", '1104report', '"', '"1104report"'),
    ("postgresql", 'Mixed Case.\"scope', '"', '"Mixed Case.\"\"scope"'),
    ("mysql", '1104report', '`', '`1104report`'),
    ("mysql", 'reg-report-analysis', '`', '`reg-report-analysis`'),
    ("mysql", 'Mixed Case.`scope', '`', '`Mixed Case.``scope`'),
])
def test_qualified_identifiers_preserve_names_and_frontend_backend_parity(tmp_path, db_type, scope, quote, expected_scope):
    payload = _structured_payload(datasource_type=db_type)
    table = payload["tables"][0]
    table.update(schema=scope, table_name='1104.Order-' + quote + 'name',
                 limit_report_period=True, report_period_field='Date Field', report_period_field_source='MANUAL')
    table["fields"][0]["column_name"] = 'select' + quote + 'Field'
    table["conditions"][0]["column_name"] = 'Condition.Name'
    content = parse_structured_content(payload)
    script = generate_script(content, report_period="2026-10-01")
    quoted = lambda name: quote + name.replace(quote, quote * 2) + quote
    assert f'UPDATE {expected_scope}.{quoted(table["table_name"])}\n' in script
    assert f'SET {quoted(table["fields"][0]["column_name"])}' in script
    assert f'WHERE {quoted("Date Field")} = ' in script
    assert f'{quoted("Condition.Name")} IN ' in script
    assert run_preview(tmp_path, content.to_dict(), report_period="2026-10-01") == script


@pytest.mark.parametrize("table_name,expected", [
    ("dws.ta_pact_detail_dws", "dws.ta_pact_detail_dws"),
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
    assert "UPDATE t_customer\n" in script
    assert run_preview(tmp_path, content.to_dict()) == script


@pytest.mark.parametrize("db_type,scope,quote", [("postgresql", "reg-report-analysis", '"'), ("mysql", "1104report", '`')])
def test_generate_api_uses_config_scope_and_pins_real_dialect(db_type, scope, quote):
    config = SimpleNamespace(db_type=db_type, schema=scope if db_type == "postgresql" else "wrong_schema",
                             database=scope if db_type == "mysql" else "wrong_database")
    service = _service(metadata=FakeMetadata({"ds1": SimpleNamespace(name="展示名", config=config)}))
    payload = _structured_payload()
    payload["tables"][0]["schema"] = ""
    script = service.generate_script({"structured_content": payload}, ACTOR)["script"]
    assert f"UPDATE {quote}{scope}{quote}.t_customer\n" in script


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
    assert "UPDATE `1104report`.t_customer" in script
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


@pytest.mark.parametrize(
    "db_type,scope,table_name,period_field,database,expected",
    [
        (
            "postgresql",
            "reg-report-analysis",
            "am_order_dws",
            "d_cldate",
            "",
            'UPDATE "reg-report-analysis".am_order_dws\nSET order_status = \'done\'\nWHERE d_cldate = \'2026-09-30\' AND project_no = \'P001\';',
        ),
        (
            "mysql",
            "stale_schema",
            "am_projinvest_dm",
            "pin_cldate",
            "1104report",
            "UPDATE `1104report`.am_projinvest_dm\nSET invest_status = 'done'\nWHERE pin_cldate = '2026-09-30' AND project_no = 'P001';",
        ),
    ],
)
def test_screenshot_paths_keep_special_scope_quote_local_and_common_parts_plain(
    tmp_path, db_type, scope, table_name, period_field, database, expected
):
    payload = _structured_payload(datasource_type=db_type)
    table = payload["tables"][0]
    table.update(
        schema=scope,
        table_name=table_name,
        limit_report_period=True,
        report_period_field=period_field,
        report_period_field_source="MANUAL",
    )
    table["fields"] = [table["fields"][0]]
    table["fields"][0].update(column_name="order_status" if db_type == "postgresql" else "invest_status",
                               value_after="done")
    table["conditions"] = [table["conditions"][0]]
    table["conditions"][0].update(column_name="project_no", operator="=", values=["P001"])
    content = parse_structured_content(payload)
    datasources = {"ds1": {"db_type": db_type, "database": database, "schema": scope}}

    script = generate_script(content, report_period="2026-09-30", datasources=datasources)

    assert expected in script
    assert run_preview(tmp_path, content.to_dict(), report_period="2026-09-30", datasources=datasources) == script


@pytest.mark.parametrize(
    "db_type,column_name,expected",
    [
        ("postgresql", "AccountStatus", '"AccountStatus"'),
        ("mysql", "AccountStatus", "AccountStatus"),
        ("postgresql", "select", '"select"'),
        ("mysql", "select", "`select`"),
        ("postgresql", 'status"old', '"status""old"'),
        ("mysql", "status`old", "`status``old`"),
        ("postgresql", "status.code", '"status.code"'),
        ("mysql", "status.code", "`status.code`"),
        ("postgresql", "3status", '"3status"'),
        ("mysql", "3status", "`3status`"),
    ],
)
def test_dialect_identifier_quoting_is_local_and_matches_preview(tmp_path, db_type, column_name, expected):
    payload = _structured_payload(datasource_type=db_type)
    payload["tables"][0]["conditions"][0].update(column_name=column_name, values=["P001"])
    content = parse_structured_content(payload)
    script = generate_script(content)

    assert f"WHERE {expected} IN ('P001')" in script
    assert run_preview(tmp_path, content.to_dict()) == script


def test_reserved_keyword_snapshots_match_frontend_and_sqlalchemy_dialects():
    module_dir = ROOT / "src" / "auto_check" / "modules" / "report_special_processing"
    js_source = (module_dir / "web" / "components" / "script_preview.js").read_text(encoding="utf-8")
    from auto_check.modules.report_special_processing import sql_builder

    js_pg = _javascript_keyword_words(js_source, "PG_RESERVED_WORDS")
    js_mysql = _javascript_keyword_words(js_source, "MYSQL_RESERVED_WORDS")
    py_pg = getattr(sql_builder, "_PG_RESERVED_WORDS", None)
    py_mysql = getattr(sql_builder, "_MYSQL_RESERVED_WORDS", None)

    assert py_pg is not None
    assert py_mysql is not None
    assert py_pg == js_pg == {word.lower() for word in RESERVED_WORDS}
    assert py_mysql == js_mysql == {word.lower() for word in RESERVED_WORDS_MYSQL}
