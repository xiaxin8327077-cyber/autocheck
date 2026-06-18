from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from auto_check.app.config import default_config_path, load_store, resolve_data_source
from auto_check.app.db import DatabaseClient
from auto_check.db_validation.schema_ddl import (
    build_postgres_alter_type_sql,
    mysql_type_to_postgres,
    parse_mysql_create_tables,
    quote_pg,
)
from auto_check.db_validation.tables import ZG_TABLES, previous_table_name


BASEINFO_TYPES: dict[str, str] = {
    "id": "varchar(64)",
    "sys_manage_id": "varchar(64)",
    "classification_id": "varchar(64)",
    "table_name_en": "varchar(128)",
    "table_name_zh": "varchar(256)",
    "table_type": "varchar(32)",
    "report_type": "integer",
    "autom_found_table": "varchar(32)",
    "apply_enabled": "varchar(32)",
    "general_earch": "text",
    "advanced_query": "text",
    "bulk_edit": "text",
    "bulk_delete": "text",
    "template_type": "varchar(32)",
    "template_json": "text",
    "template_field_list": "text",
    "form_operation_json": "text",
    "btn_manage_json": "text",
    "group_census_jons": "text",
    "menu_merge_code": "varchar(64)",
    "menu_merge_json": "text",
    "individuation_json": "text",
    "del_flag": "varchar(16)",
    "remarks": "text",
    "table_verify_enabled": "varchar(32)",
    "create_by": "varchar(64)",
    "create_date": "timestamp",
    "update_by": "varchar(64)",
    "update_date": "timestamp",
    "data_source_Id": "varchar(64)",
    "use_sql": "text",
    "sql_list": "text",
    "sql_total": "text",
    "result_area_json": "text",
    "import_json": "text",
    "record_count_sql": "text",
    "record_sql_id": "varchar(64)",
    "record_sql": "text",
    "is_complete": "integer",
    "head_search": "text",
    "create_type": "integer",
    "index_id": "varchar(64)",
    "update_msg": "text",
    "update_state": "integer",
    "sort": "integer",
    "ency": "varchar(32)",
    "archive_cycle": "varchar(32)",
    "add_table": "varchar(32)",
    "whether_archive": "varchar(32)",
    "datasource_en_name": "varchar(128)",
    "create_table_mode": "varchar(32)",
    "version_no": "varchar(32)",
    "archive_type": "varchar(32)",
}

FIELD_INFO_TYPES: dict[str, str] = {
    "id": "varchar(128)",
    "table_id": "varchar(64)",
    "field_length": "varchar(32)",
    "sort": "integer",
    "field_propert": "varchar(128)",
    "field_name": "varchar(255)",
    "filed_key": "varchar(32)",
    "table_type": "varchar(32)",
    "def_value": "text",
    "fill_value": "text",
    "field_input": "varchar(32)",
    "dick_type": "varchar(32)",
    "dick_value": "text",
    "query_proper": "varchar(128)",
    "filed_show": "varchar(32)",
    "modify_whether": "integer",
    "batch_modify": "integer",
    "remarks": "text",
    "form_script": "text",
    "list_script": "text",
    "write_only": "varchar(32)",
    "index_id": "varchar(64)",
    "field_type": "varchar(32)",
    "parent_id": "varchar(64)",
    "desensitize": "varchar(32)",
    "notes": "text",
    "is_null_empty": "varchar(32)",
    "encry": "varchar(32)",
    "export_type": "varchar(32)",
    "archive_desensitize": "varchar(32)",
    "splicing_field": "varchar(32)",
    "identity_type": "varchar(32)",
    "determ_desen": "varchar(32)",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair local db-validation table column types from metadata DDL.")
    parser.add_argument("--rhzbbs-sql", default=r"D:\xiaxin\download\rhzbbs.sql")
    parser.add_argument("--report-date", default="2026-05-31")
    parser.add_argument("--apply", action="store_true", help="Execute ALTER TABLE statements. Default prints SQL only.")
    parser.add_argument("--output", default=str(ROOT / "verification" / "db_validation_schema_repair.sql"))
    args = parser.parse_args()

    store = load_store(default_config_path())
    settings = store.db_validation
    detail_source = resolve_data_source(store, settings.detail.source_id)
    metadata_source = resolve_data_source(store, settings.field_mapping_source_id or settings.detail.source_id)
    if detail_source.db_type != "postgresql" or metadata_source.db_type != "postgresql":
        raise SystemExit("This repair script currently targets the local PostgreSQL test database.")

    report_date = date.fromisoformat(args.report_date)
    ddl_text = _read_sql_text(Path(args.rhzbbs_sql))
    mysql_schemas = parse_mysql_create_tables(ddl_text)

    statements: list[str] = []
    statements.extend(_detail_table_statements(detail_source.schema or "public", report_date, mysql_schemas))
    statements.extend(_metadata_table_statements(metadata_source.schema or "public", settings.baseinfo_table, BASEINFO_TYPES))
    statements.extend(_metadata_table_statements(metadata_source.schema or "public", settings.field_info_table, FIELD_INFO_TYPES))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(statements) + "\n", encoding="utf-8")
    print(f"SQL statements: {len(statements)}")
    print(f"SQL file: {output}")

    if args.apply:
        _execute_statements(detail_source, metadata_source, statements)
        print("Applied schema repair.")
    return 0


def _read_sql_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gbk", "utf-8"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("gbk", errors="replace")


def _detail_table_statements(schema: str, report_date: date, mysql_schemas: dict) -> list[str]:
    statements: list[str] = []
    for base_table in ZG_TABLES.values():
        table_schema = mysql_schemas.get(base_table)
        if table_schema is None:
            continue
        for table_name in (base_table, previous_table_name(base_table, report_date)):
            for column in table_schema.columns:
                pg_type = mysql_type_to_postgres(column.mysql_type)
                statements.append(build_postgres_alter_type_sql(schema, table_name, column.name, pg_type))
    return statements


def _metadata_table_statements(schema: str, table: str, column_types: dict[str, str]) -> list[str]:
    return [build_postgres_alter_type_sql(schema, table, column, pg_type) for column, pg_type in column_types.items()]


def _execute_statements(detail_source, metadata_source, statements: list[str]) -> None:
    # Current local config points both sources to the same PostgreSQL database. If that changes,
    # execute statements through both connections and ignore statements for missing tables.
    clients = [DatabaseClient(detail_source)]
    if (
        metadata_source.host,
        metadata_source.port,
        metadata_source.database,
        metadata_source.username,
    ) != (
        detail_source.host,
        detail_source.port,
        detail_source.database,
        detail_source.username,
    ):
        clients.append(DatabaseClient(metadata_source))
    for client in clients:
        with client._connect() as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                for statement in statements:
                    try:
                        cursor.execute(statement)
                    except Exception as exc:
                        if "does not exist" in str(exc):
                            continue
                        raise


if __name__ == "__main__":
    raise SystemExit(main())
