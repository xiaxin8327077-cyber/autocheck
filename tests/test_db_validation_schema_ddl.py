from auto_check.db_validation.schema_ddl import (
    build_postgres_alter_type_sql,
    mysql_type_to_postgres,
    parse_mysql_create_tables,
)


def test_parse_mysql_create_tables_extracts_column_types():
    ddl = """
    CREATE TABLE `zg01` (
      `projcode` varchar(100) CHARACTER SET utf8mb3 COLLATE utf8mb3_bin DEFAULT NULL COMMENT '产品代码',
      `reserve4` int DEFAULT NULL COMMENT '最短开放周期',
      `caldate` date DEFAULT NULL COMMENT '报告期',
      `tbtime` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '同步时间'
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """

    tables = parse_mysql_create_tables(ddl)

    assert [column.name for column in tables["zg01"].columns] == ["projcode", "reserve4", "caldate", "tbtime"]
    assert [column.mysql_type for column in tables["zg01"].columns] == ["varchar(100)", "int", "date", "datetime"]


def test_mysql_type_to_postgres_converts_supported_types():
    assert mysql_type_to_postgres("varchar(100)") == "varchar(100)"
    assert mysql_type_to_postgres("date") == "date"
    assert mysql_type_to_postgres("datetime") == "timestamp"
    assert mysql_type_to_postgres("int") == "integer"
    assert mysql_type_to_postgres("decimal(23,2)") == "numeric(23,2)"


def test_build_postgres_alter_type_sql_casts_empty_values_to_null_for_typed_columns():
    assert build_postgres_alter_type_sql("dws", "zg01", "caldate", "date") == (
        'ALTER TABLE "dws"."zg01" ALTER COLUMN "caldate" TYPE date '
        "USING CASE WHEN NULLIF(\"caldate\", '') IS NULL THEN NULL "
        "WHEN \"caldate\" ~ '^\\d{8}$' THEN to_date(\"caldate\", 'YYYYMMDD') "
        'ELSE "caldate"::date END;'
    )
    assert build_postgres_alter_type_sql("dws", "zg01", "reserve4", "integer") == (
        'ALTER TABLE "dws"."zg01" ALTER COLUMN "reserve4" TYPE integer '
        "USING CASE WHEN NULLIF(\"reserve4\", '') IS NULL THEN NULL ELSE (\"reserve4\"::numeric)::integer END;"
    )
