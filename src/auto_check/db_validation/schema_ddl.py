from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    mysql_type: str


@dataclass(frozen=True)
class TableSchema:
    name: str
    columns: tuple[ColumnSchema, ...]


CREATE_TABLE_RE = re.compile(r"CREATE TABLE `(?P<table>[^`]+)` \((?P<body>.*?)\) ENGINE=", re.S | re.I)
COLUMN_RE = re.compile(r"^\s*`(?P<name>[^`]+)`\s+(?P<definition>.+?)\s*,?\s*$", re.S)


def parse_mysql_create_tables(sql: str) -> dict[str, TableSchema]:
    tables: dict[str, TableSchema] = {}
    for match in CREATE_TABLE_RE.finditer(sql):
        table_name = match.group("table")
        columns: list[ColumnSchema] = []
        for raw_line in match.group("body").splitlines():
            line = raw_line.rstrip().rstrip(",")
            column_match = COLUMN_RE.match(line)
            if not column_match:
                continue
            columns.append(
                ColumnSchema(
                    name=column_match.group("name"),
                    mysql_type=_extract_mysql_type(column_match.group("definition")),
                )
            )
        tables[table_name] = TableSchema(name=table_name, columns=tuple(columns))
    return tables


def mysql_type_to_postgres(mysql_type: str) -> str:
    value = mysql_type.lower().strip()
    if value.startswith("varchar"):
        return value
    if value.startswith("char"):
        return value
    if value in {"text", "tinytext", "mediumtext", "longtext"}:
        return "text"
    if value == "date":
        return "date"
    if value in {"datetime", "timestamp"}:
        return "timestamp"
    if value in {"int", "integer"}:
        return "integer"
    if value == "bigint":
        return "bigint"
    if value == "smallint":
        return "smallint"
    if value == "tinyint":
        return "smallint"
    if value.startswith("decimal"):
        return value.replace("decimal", "numeric", 1)
    if value.startswith("double"):
        return "double precision"
    if value.startswith("float"):
        return "real"
    return "text"


def postgres_cast_expression(column_name: str, postgres_type: str) -> str:
    quoted = quote_pg(column_name)
    normalized = postgres_type.lower()
    if normalized == "date":
        return (
            f"CASE WHEN NULLIF({quoted}, '') IS NULL THEN NULL "
            f"WHEN {quoted} ~ '^\\d{{8}}$' THEN to_date({quoted}, 'YYYYMMDD') "
            f"ELSE {quoted}::date END"
        )
    if normalized == "timestamp":
        return (
            f"CASE WHEN NULLIF({quoted}, '') IS NULL THEN NULL "
            f"WHEN {quoted} ~ '^\\d{{8}}$' THEN to_timestamp({quoted}, 'YYYYMMDD') "
            f"ELSE {quoted}::timestamp END"
        )
    if normalized in {"integer", "bigint", "smallint"}:
        return f"CASE WHEN NULLIF({quoted}, '') IS NULL THEN NULL ELSE ({quoted}::numeric)::{normalized} END"
    if normalized.startswith("numeric") or normalized in {"real", "double precision"}:
        return f"CASE WHEN NULLIF({quoted}, '') IS NULL THEN NULL ELSE {quoted}::{postgres_type} END"
    return f"{quoted}::{postgres_type}"


def build_postgres_alter_type_sql(schema: str, table: str, column: str, postgres_type: str) -> str:
    return (
        f"ALTER TABLE {quote_pg(schema)}.{quote_pg(table)} "
        f"ALTER COLUMN {quote_pg(column)} TYPE {postgres_type} "
        f"USING {postgres_cast_expression(column, postgres_type)};"
    )


def quote_pg(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _extract_mysql_type(definition: str) -> str:
    value = definition.strip()
    value = re.split(r"\s+COMMENT\s+", value, maxsplit=1, flags=re.I)[0]
    value = re.sub(r"\s+CHARACTER SET\s+\S+", "", value, flags=re.I)
    value = re.sub(r"\s+COLLATE\s+\S+", "", value, flags=re.I)
    value = re.sub(r"\s+DEFAULT\s+CURRENT_TIMESTAMP(?:\(\))?", "", value, flags=re.I)
    value = re.sub(r"\s+DEFAULT\s+'[^']*'", "", value, flags=re.I)
    value = re.sub(r"\s+DEFAULT\s+\S+", "", value, flags=re.I)
    value = re.sub(r"\s+NOT\s+NULL", "", value, flags=re.I)
    value = re.sub(r"\s+NULL", "", value, flags=re.I)
    return value.strip().lower()
