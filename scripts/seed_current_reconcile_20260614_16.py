from __future__ import annotations

from typing import Any

from auto_check.app.config import load_store, normalize_store, resolve_data_source
from auto_check.app.db import DatabaseClient


DATES = ("2026-06-14", "2026-06-15", "2026-06-16")
PREFIXES = ("AC20260614", "AC20260615", "AC20260616")


PROJECT_ROWS = [
    ("2026-06-14", "AC20260614UNK01", "2026-06-14 unknown without valuation total", 1000000, 900000, 300000),
    ("2026-06-14", "AC20260614AM01", "2026-06-14 asset missing single bond", 900000, 1000000, 300000),
    ("2026-06-14", "AC20260614AD01", "2026-06-14 asset duplicate single bond", 1100000, 1000000, 300000),
    ("2026-06-14", "AC20260614DIFF01", "2026-06-14 asset difference loan full match", 1050000, 1000000, 300000),
    ("2026-06-15", "AC20260615RTMISS01", "2026-06-15 received trust missing", 1000000, 900000, 0),
    ("2026-06-15", "AC20260615RTDUP01", "2026-06-15 received trust duplicate", 1000000, 1100000, 200000),
    ("2026-06-15", "AC20260615RTDIFF01", "2026-06-15 received trust difference", 1000000, 980000, 80000),
    ("2026-06-15", "AC20260615LEMISS01", "2026-06-15 liability equity missing", 1000000, 900000, 300000),
    ("2026-06-15", "AC20260615LEDUP01", "2026-06-15 liability equity duplicate", 1000000, 1100000, 300000),
    ("2026-06-15", "AC20260615LEDIFF01", "2026-06-15 liability equity positive repo difference", 1000000, 900000, 300000),
    ("2026-06-16", "AC20260616MIX01", "2026-06-16 received trust plus liability", 1000000, 850000, 280000),
    ("2026-06-16", "AC20260616COMA01", "2026-06-16 common receivable asset missing", 900000, 1000000, 300000),
    ("2026-06-16", "AC20260616COMP01", "2026-06-16 common payable liability missing", 1000000, 920000, 300000),
    ("2026-06-16", "AC20260616AMB01", "2026-06-16 asset missing ambiguous candidates", 900000, 1000000, 300000),
    ("2026-06-16", "AC20260616BOND01", "2026-06-16 bond DM asset difference", 1050000, 1000000, 300000),
]

FA_ROWS = [
    (code, day, "4001", "received trust principal", balance)
    for day, code, _name, _a0001, _d0000, balance in PROJECT_ROWS
]
FA_ROWS[4] = ("AC20260615RTMISS01", "2026-06-15", "4001", "received trust principal", 100000)
FA_ROWS[5] = ("AC20260615RTDUP01", "2026-06-15", "4001", "received trust principal", 100000)
FA_ROWS[6] = ("AC20260615RTDIFF01", "2026-06-15", "4001", "received trust principal", 100000)
FA_ROWS[10] = ("AC20260616MIX01", "2026-06-16", "4001", "received trust principal", 300000)

VALUATION_ROWS = [
    ("AC20260614AM01", "ACASSET1401", "2026-06-14", "0004", "asset total", 1000000),
    ("AC20260614AM01", "ACASSET1401", "2026-06-14", "1501.01.02.01.BOND1401", "scenario bond 1401", 100000),
    ("AC20260614AD01", "ACASSET1402", "2026-06-14", "0004", "asset total", 1000000),
    ("AC20260614AD01", "ACASSET1402", "2026-06-14", "1501.01.02.01.BOND1402", "scenario bond 1402", 100000),
    ("AC20260614DIFF01", "ACASSET1403", "2026-06-14", "0004", "asset total", 1000000),
    ("AC20260614DIFF01", "ACASSET1403", "2026-06-14", "1303.01.01.01.DK2026061401", "scenario loan 1401", 100000),
    ("AC20260615RTMISS01", "ACASSET1501", "2026-06-15", "0004", "asset total", 1000000),
    ("AC20260615RTDUP01", "ACASSET1502", "2026-06-15", "0004", "asset total", 1000000),
    ("AC20260615RTDIFF01", "ACASSET1503", "2026-06-15", "0004", "asset total", 1000000),
    ("AC20260615LEMISS01", "ACASSET1504", "2026-06-15", "0004", "asset total", 1000000),
    ("AC20260615LEMISS01", "ACASSET1504", "2026-06-15", "2001.01", "scenario payable management fee", 100000),
    ("AC20260615LEDUP01", "ACASSET1505", "2026-06-15", "0004", "asset total", 1000000),
    ("AC20260615LEDUP01", "ACASSET1505", "2026-06-15", "2001.02", "scenario duplicated payable", 100000),
    ("AC20260615LEDIFF01", "ACASSET1506", "2026-06-15", "0004", "asset total", 1000000),
    ("AC20260615LEDIFF01", "ACASSET1506", "2026-06-15", "2111.01.01.01.RP2026061501", "scenario positive repo", 150000),
    ("AC20260616MIX01", "ACASSET1601", "2026-06-16", "0004", "asset total", 1000000),
    ("AC20260616MIX01", "ACASSET1601", "2026-06-16", "2203.02.01.01.FEE1601", "scenario operation fee", 130000),
    ("AC20260616COMA01", "ACASSET1602", "2026-06-16", "0004", "asset total", 1000000),
    ("AC20260616COMA01", "ACASSET1602", "2026-06-16", "3001.01", "scenario common receivable", 100000),
    ("AC20260616COMP01", "ACASSET1603", "2026-06-16", "0004", "asset total", 1000000),
    ("AC20260616COMP01", "ACASSET1603", "2026-06-16", "3001.02", "scenario common payable", -80000),
    ("AC20260616AMB01", "ACASSET1604", "2026-06-16", "0004", "asset total", 1000000),
    ("AC20260616AMB01", "ACASSET1604", "2026-06-16", "1501.01.02.01.BOND1604A", "scenario ambiguous bond A", 60000),
    ("AC20260616AMB01", "ACASSET1604", "2026-06-16", "1501.01.02.01.BOND1604B", "scenario ambiguous bond B", 40000),
    ("AC20260616AMB01", "ACASSET1604", "2026-06-16", "1501.01.02.01.BOND1604C", "scenario ambiguous bond C", 60000),
    ("AC20260616AMB01", "ACASSET1604", "2026-06-16", "1501.01.02.01.BOND1604D", "scenario ambiguous bond D", 40000),
    ("AC20260616BOND01", "ACASSET1605", "2026-06-16", "0004", "asset total", 1000000),
    ("AC20260616BOND01", "ACASSET1605", "2026-06-16", "1501.01.02.01.BOND1605", "scenario DM bond 1605", 100000),
]

DM_PROJECT_INVEST_ROWS = [
    ("AC20260614DIFF01", "2026-06-14", "DK2026061401", 150000, None),
]

DM_SECURITY_ROWS = [
    ("AC20260616BOND01", "2026-06-16", "BOND1605", "scenario DM bond 1605", 150000, 0, 0, "01", None, None),
]

PLEDGE_ROWS = [
    ("AC20260615LEDIFF01", "8001501", 60000, 10000),
]


def main() -> None:
    store = normalize_store(load_store())
    dws_config = resolve_data_source(store, store.reconcile_data_sources.dws_source_id)
    business_config = resolve_data_source(store, store.reconcile_data_sources.business_source_id)
    if dws_config.db_type != "postgresql":
        raise SystemExit(f"DWS source must be PostgreSQL, got {dws_config.db_type}")
    if business_config.db_type != "mysql":
        raise SystemExit(f"Business source must be MySQL, got {business_config.db_type}")

    dws = DatabaseClient(dws_config)
    business = DatabaseClient(business_config)
    _seed_postgres(dws, dws_config.schema or "public")
    _seed_mysql(business, business_config.schema or business_config.database)
    print("Seeded AC20260614/AC20260615/AC20260616 reconcile scenarios into current app data sources.")


def _seed_postgres(client: DatabaseClient, dws_schema: str) -> None:
    q_dws = _pg_ident(dws_schema)
    with client._connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {q_dws}")
            cursor.execute('CREATE SCHEMA IF NOT EXISTS "dm"')
            cursor.execute('CREATE SCHEMA IF NOT EXISTS "zgxg_zhbs"')
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_dws}."fa_accountbalance_dws" (
                  c_projcode varchar,
                  d_balancedate date,
                  c_accountcode varchar,
                  c_accountname varchar,
                  f_balance numeric
                )
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_dws}."fa_valuationreport_dws" (
                  c_projcode varchar,
                  c_assetcode varchar,
                  d_valuationdate date,
                  c_accountcode varchar,
                  c_accountname varchar,
                  f_marketvalue numeric
                )
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_dws}."ta_pact_detail_dws" (
                  d_cldate date,
                  c_projcode varchar,
                  c_pactid varchar,
                  f_shareamt numeric,
                  f_alltincom numeric
                )
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_dws}."am_pactasset_dws" (
                  c_projcode varchar,
                  d_cldate date,
                  c_pactid varchar,
                  c_udlyasset varchar,
                  c_stockcode varchar,
                  c_spv_type varchar,
                  c_assettype varchar
                )
                """
            )
            cursor.execute(f'ALTER TABLE {q_dws}."am_pactasset_dws" ADD COLUMN IF NOT EXISTS c_spv_type varchar')
            cursor.execute(f'ALTER TABLE {q_dws}."am_pactasset_dws" ADD COLUMN IF NOT EXISTS c_assettype varchar')
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_dws}."am_projinvest_dws" (
                  c_projcode varchar,
                  d_cldate date,
                  c_pactid varchar,
                  f_acbalance numeric
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS "dm"."fa_security_balance_zgxg_dm" (
                  sbm_projcode varchar,
                  sbm_cacldate date,
                  sbm_stockcode varchar,
                  sbm_sename varchar,
                  sbm_balamoney_cost numeric,
                  sbm_balamoney_fair numeric,
                  sbm_balamoney_inte numeric,
                  sbm_seclas_h2024 varchar,
                  sbm_gpgqtype_h varchar,
                  sbm_fundtype varchar
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS "dm"."am_projinvest_zgxg_dm" (
                  pin_projcode varchar,
                  pin_cldate date,
                  pin_mpactid varchar,
                  pin_acbalance numeric,
                  pin_gqtype_h varchar
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS "dm"."ta_pact_survamt_day_zgxg_dm" (
                  tpm_date date,
                  tpm_tcmpcode varchar,
                  tpm_pactid varchar,
                  tpm_clientname varchar,
                  tpm_clientkind_tusp varchar,
                  tpm_clientkindex varchar,
                  tpm_spvtype varchar,
                  tpm_htincome numeric,
                  tpm_shareamt numeric
                )
                """
            )
            cursor.execute(_delete_sql(f'{q_dws}."fa_accountbalance_dws"', "d_balancedate", "c_projcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(_delete_sql(f'{q_dws}."fa_valuationreport_dws"', "d_valuationdate", "c_projcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(_delete_sql(f'{q_dws}."ta_pact_detail_dws"', "d_cldate", "c_projcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(_delete_sql(f'{q_dws}."am_pactasset_dws"', "d_cldate", "c_projcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(_delete_sql(f'{q_dws}."am_projinvest_dws"', "d_cldate", "c_projcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(_delete_sql('"dm"."fa_security_balance_zgxg_dm"', "sbm_cacldate", "sbm_projcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(_delete_sql('"dm"."am_projinvest_zgxg_dm"', "pin_cldate", "pin_projcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(_delete_sql('"dm"."ta_pact_survamt_day_zgxg_dm"', "tpm_date", "tpm_tcmpcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.executemany(
                f"INSERT INTO {q_dws}.\"fa_accountbalance_dws\" (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES (%s, %s, %s, %s, %s)",
                FA_ROWS,
            )
            cursor.executemany(
                f"INSERT INTO {q_dws}.\"fa_valuationreport_dws\" (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES (%s, %s, %s, %s, %s, %s)",
                VALUATION_ROWS,
            )
            cursor.executemany(
                'INSERT INTO "dm"."am_projinvest_zgxg_dm" (pin_projcode, pin_cldate, pin_mpactid, pin_acbalance, pin_gqtype_h) VALUES (%s, %s, %s, %s, %s)',
                DM_PROJECT_INVEST_ROWS,
            )
            cursor.executemany(
                'INSERT INTO "dm"."fa_security_balance_zgxg_dm" (sbm_projcode, sbm_cacldate, sbm_stockcode, sbm_sename, sbm_balamoney_cost, sbm_balamoney_fair, sbm_balamoney_inte, sbm_seclas_h2024, sbm_gpgqtype_h, sbm_fundtype) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                DM_SECURITY_ROWS,
            )
        connection.commit()


def _seed_mysql(client: DatabaseClient, business_db: str) -> None:
    q_business = _mysql_ident(business_db)
    with client._connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_business}.`zf_detail_2024` (
                  caldate date NOT NULL,
                  projinnercode varchar(100) NOT NULL,
                  projname varchar(255) NOT NULL,
                  a0001 decimal(24, 2) NOT NULL,
                  d0000 decimal(24, 2) NOT NULL,
                  c1000 decimal(24, 2) NOT NULL
                )
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_business}.`currency_report_duration` (
                  id1 varchar(255) PRIMARY KEY,
                  caldate date,
                  c_projectcode varchar(100),
                  c_projectname varchar(255),
                  f_assetshare decimal(24, 2)
                )
                """
            )
            cursor.execute("CREATE DATABASE IF NOT EXISTS `currency_report_24`")
            for table in [
                "currency_detail_project_2_1_2",
                "currency_detail_project_2_1_4",
                "currency_detail_project_2_1_5",
                "currency_detail_project_2_1_5_2",
                "currency_detail_project_2_1_6",
                "currency_detail_project_2_1_8",
                "currency_detail_project_2_1_9",
            ]:
                cursor.execute(f"CREATE TABLE IF NOT EXISTS `currency_report_24`.`{table}` (caldate date)")
                cursor.execute(
                    f"DELETE FROM `currency_report_24`.`{table}` WHERE caldate IN (%s, %s, %s)",
                    DATES,
                )
                cursor.executemany(
                    f"INSERT INTO `currency_report_24`.`{table}` (caldate) VALUES (%s)",
                    [(day,) for day in DATES],
                )
            cursor.execute("CREATE DATABASE IF NOT EXISTS `assman_reg`")
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS `assman_reg`.`ex_pledge_back` (
                  project_code varchar(100),
                  subcode varchar(100),
                  buyback_money decimal(24, 2),
                  expenses decimal(24, 2)
                )
                """
            )
            cursor.execute(_delete_sql(f"{q_business}.`zf_detail_2024`", "caldate", "projinnercode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(_delete_sql(f"{q_business}.`currency_report_duration`", "caldate", "c_projectcode"), (*DATES, *[f"{prefix}%" for prefix in PREFIXES]))
            cursor.execute(
                "DELETE FROM `assman_reg`.`ex_pledge_back` WHERE project_code LIKE %s OR project_code LIKE %s OR project_code LIKE %s",
                tuple(f"{prefix}%" for prefix in PREFIXES),
            )
            cursor.executemany(
                f"INSERT INTO {q_business}.`zf_detail_2024` (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES (%s, %s, %s, %s, %s, %s)",
                PROJECT_ROWS,
            )
            currency_rows = [
                (f"CRD-20260614-16-{code}", day, code, name, c1000)
                for day, code, name, _a0001, _d0000, c1000 in PROJECT_ROWS
            ]
            cursor.executemany(
                f"INSERT INTO {q_business}.`currency_report_duration` (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES (%s, %s, %s, %s, %s)",
                currency_rows,
            )
            cursor.executemany(
                "INSERT INTO `assman_reg`.`ex_pledge_back` (project_code, subcode, buyback_money, expenses) VALUES (%s, %s, %s, %s)",
                PLEDGE_ROWS,
            )
        connection.commit()


def _delete_sql(table: str, date_col: str, code_col: str) -> str:
    return (
        f"DELETE FROM {table} "
        f"WHERE {date_col} IN (%s, %s, %s) "
        f"AND ({code_col} LIKE %s OR {code_col} LIKE %s OR {code_col} LIKE %s)"
    )


def _pg_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _mysql_ident(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


if __name__ == "__main__":
    main()
