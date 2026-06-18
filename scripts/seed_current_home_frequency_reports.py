from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from auto_check.app.config import AppConfig, load_store, normalize_store, resolve_data_source
from auto_check.app.db import DatabaseClient, qualified_name
from auto_check.app.local_store import db_path_for_config, list_history_runs
from auto_check.app.server import ApiRouter


REPORT_DATES = (
    "2026-06-17",
    "2026-06-18",
    "2026-06-19",
    "2026-06-20",
    "2026-06-21",
    "2026-06-22",
)
PROJECT_PREFIX = "HFJST2026"
HISTORY_EXECUTOR_ID = "seed-home-frequency-reports"


def main() -> None:
    store = normalize_store(load_store())
    config_path = Path.home() / "AppData" / "Roaming" / "auto-check" / "config.json"
    dws_config = resolve_data_source(store, store.reconcile_data_sources.dws_source_id)
    business_config = resolve_data_source(store, store.reconcile_data_sources.business_source_id)
    config = AppConfig(dws=dws_config, business=business_config)

    if dws_config.db_type != "postgresql":
        raise SystemExit(f"DWS source must be PostgreSQL, got {dws_config.db_type}")
    if business_config.db_type != "mysql":
        raise SystemExit(f"Business source must be MySQL, got {business_config.db_type}")

    _seed_dws(DatabaseClient(dws_config), dws_config.schema or "public")
    _seed_business(DatabaseClient(business_config), business_config.schema or business_config.database)
    _delete_previous_generated_history(config_path)
    _run_reconcile_history(config_path)
    _promote_history_specific_reasons(config_path)
    _print_verification(config, config_path)


def _scenario_rows() -> tuple[
    list[tuple],
    list[tuple],
    list[tuple],
    list[tuple],
    list[tuple],
    list[tuple],
    list[tuple],
]:
    projects = []
    fa_balances = []
    valuations = []
    pact_assets = []
    dm_project_invest = []
    pledge_rows = []
    currency_rows = []

    for index, day in enumerate(REPORT_DATES):
        period_no = index + 1

        supply_total = Decimal("128000000") + Decimal(index * 420000)
        supply_gap = Decimal("240000") + Decimal(index * 15000)
        supply_asset = supply_total - supply_gap
        projects.append((day, "HFJST2026GYS001", "江苏信托-锡澄供应链1号集合资金信托计划", supply_asset, supply_total, Decimal("36000000")))
        fa_balances.append(("HFJST2026GYS001", day, "4001", "实收信托", Decimal("36000000")))
        valuations.extend([
            ("HFJST2026GYS001", f"HF-GYS-{period_no:02d}", day, "0004", "资产合计", supply_total),
            ("HFJST2026GYS001", f"HF-GYS-{period_no:02d}", day, f"1501.01.02.01.GYS{period_no:04d}", "锡澄供应链应收账款支持票据", supply_gap),
        ])

        trust_total = Decimal("216000000") + Decimal(index * 530000)
        trust_diff = Decimal("185000") + Decimal(index * 12000)
        projects.append((day, "HFJST2026SXB002", "江苏信托-苏信宝现金管理集合资金信托计划", trust_total, trust_total - trust_diff, Decimal("52000000")))
        fa_balances.append(("HFJST2026SXB002", day, "4001", "实收信托", Decimal("52000000") + trust_diff))
        valuations.append(("HFJST2026SXB002", f"HF-SXB-{period_no:02d}", day, "0004", "资产合计", trust_total))

        park_total = Decimal("342000000") + Decimal(index * 610000)
        park_gap = Decimal("160000") + Decimal(index * 10000)
        projects.append((day, "HFJST2026JBC003", "江苏信托-江北科创园运营收益权集合资金信托计划", park_total, park_total - park_gap, Decimal("88000000")))
        fa_balances.append(("HFJST2026JBC003", day, "4001", "实收信托", Decimal("88000000")))
        valuations.extend([
            ("HFJST2026JBC003", f"HF-JBC-{period_no:02d}", day, "0004", "资产合计", park_total),
            ("HFJST2026JBC003", f"HF-JBC-{period_no:02d}", day, f"2203.02.01.01.FEE{period_no:04d}", "应付托管运营费用-江北科创园", park_gap),
        ])

        loan_total = Decimal("176000000") + Decimal(index * 390000)
        loan_gap = Decimal("72000") + Decimal(index * 8000)
        loan_account = f"DK202606{17 + index:02d}01"
        projects.append((day, "HFJST2026SZD004", "江苏信托-苏州高新区流动资金贷款集合资金信托计划", loan_total + loan_gap, loan_total, Decimal("43000000")))
        fa_balances.append(("HFJST2026SZD004", day, "4001", "实收信托", Decimal("43000000")))
        valuations.extend([
            ("HFJST2026SZD004", f"HF-SZD-{period_no:02d}", day, "0004", "资产合计", loan_total),
            ("HFJST2026SZD004", f"HF-SZD-{period_no:02d}", day, f"1303.01.01.01.{loan_account}", "苏州高新区流动资金贷款", Decimal("900000")),
        ])
        dm_project_invest.append(("HFJST2026SZD004", day, loan_account, Decimal("900000") + loan_gap, None))

        repo_total = Decimal("268000000") + Decimal(index * 440000)
        repo_gap = Decimal("98000") + Decimal(index * 7000)
        projects.append((day, "HFJST2026NHR005", "江苏信托-宁沪短融回购增强集合资金信托计划", repo_total, repo_total - repo_gap, Decimal("64000000")))
        fa_balances.append(("HFJST2026NHR005", day, "4001", "实收信托", Decimal("64000000")))
        valuations.extend([
            ("HFJST2026NHR005", f"HF-NHR-{period_no:02d}", day, "0004", "资产合计", repo_total),
            ("HFJST2026NHR005", f"HF-NHR-{period_no:02d}", day, f"2111.06.03.01.RP{period_no:04d}", "银行间质押式正回购", Decimal("1200000") + repo_gap),
        ])
        if index == 0:
            pledge_rows.append(("HFJST2026NHR005", "800001", Decimal("1200000"), Decimal("0")))

        spv_total = Decimal("154000000") + Decimal(index * 360000)
        spv_gap = Decimal("210000") + Decimal(index * 9000)
        projects.append((day, "HFJST2026XTB006", "江苏信托-苏信稳盈特定目的载体集合资金信托计划", spv_total - spv_gap, spv_total, Decimal("41000000")))
        fa_balances.append(("HFJST2026XTB006", day, "4001", "实收信托", Decimal("41000000")))
        valuations.extend([
            ("HFJST2026XTB006", f"HF-XTB-{period_no:02d}", day, "0004", "资产合计", spv_total),
            ("HFJST2026XTB006", f"HF-XTB-{period_no:02d}", day, "1101.05.03.01.XTB006", "苏信稳盈特定目的载体", spv_gap),
        ])
        pact_assets.append(("HFJST2026XTB006", day, f"PACT-XTB-{period_no:02d}", "苏信稳盈特定目的载体", "XTB999", "10", "31"))

        if day == REPORT_DATES[-1]:
            projects.append((day, "HFJST2026WTZ999", "江苏信托-江南稳健投资组合集合资金信托计划", Decimal("92000000"), Decimal("91880000"), Decimal("26000000")))
            fa_balances.append(("HFJST2026WTZ999", day, "4001", "实收信托", Decimal("26000000")))

    for day, code, name, _a0001, _d0000, c1000 in projects:
        currency_rows.append((f"CRD-HF-{day}-{code}", day, code, name, c1000))

    return projects, fa_balances, valuations, pact_assets, dm_project_invest, pledge_rows, currency_rows


def _seed_dws(client: DatabaseClient, schema: str) -> None:
    _projects, fa_balances, valuations, pact_assets, dm_project_invest, _pledge_rows, _currency_rows = _scenario_rows()
    q_schema = _pg_ident(schema)
    with client._connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {q_schema}")
            cursor.execute('CREATE SCHEMA IF NOT EXISTS "dm"')
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_schema}."fa_accountbalance_dws" (
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
                CREATE TABLE IF NOT EXISTS {q_schema}."fa_valuationreport_dws" (
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
                CREATE TABLE IF NOT EXISTS {q_schema}."am_pactasset_dws" (
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
            cursor.execute(f'ALTER TABLE {q_schema}."am_pactasset_dws" ADD COLUMN IF NOT EXISTS c_spv_type varchar')
            cursor.execute(f'ALTER TABLE {q_schema}."am_pactasset_dws" ADD COLUMN IF NOT EXISTS c_assettype varchar')
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
            cursor.execute(_delete_sql(f'{q_schema}."fa_accountbalance_dws"', "d_balancedate", "c_projcode"), (*REPORT_DATES, f"{PROJECT_PREFIX}%"))
            cursor.execute(_delete_sql(f'{q_schema}."fa_valuationreport_dws"', "d_valuationdate", "c_projcode"), (*REPORT_DATES, f"{PROJECT_PREFIX}%"))
            cursor.execute(_delete_sql(f'{q_schema}."am_pactasset_dws"', "d_cldate", "c_projcode"), (*REPORT_DATES, f"{PROJECT_PREFIX}%"))
            cursor.execute(_delete_sql('"dm"."am_projinvest_zgxg_dm"', "pin_cldate", "pin_projcode"), (*REPORT_DATES, f"{PROJECT_PREFIX}%"))
            cursor.execute(_delete_sql('"dm"."fa_security_balance_zgxg_dm"', "sbm_cacldate", "sbm_projcode"), (*REPORT_DATES, f"{PROJECT_PREFIX}%"))
            cursor.executemany(
                f"INSERT INTO {q_schema}.\"fa_accountbalance_dws\" (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES (%s, %s, %s, %s, %s)",
                fa_balances,
            )
            cursor.executemany(
                f"INSERT INTO {q_schema}.\"fa_valuationreport_dws\" (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES (%s, %s, %s, %s, %s, %s)",
                valuations,
            )
            cursor.executemany(
                f"INSERT INTO {q_schema}.\"am_pactasset_dws\" (c_projcode, d_cldate, c_pactid, c_udlyasset, c_stockcode, c_spv_type, c_assettype) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                pact_assets,
            )
            cursor.executemany(
                'INSERT INTO "dm"."am_projinvest_zgxg_dm" (pin_projcode, pin_cldate, pin_mpactid, pin_acbalance, pin_gqtype_h) VALUES (%s, %s, %s, %s, %s)',
                dm_project_invest,
            )
        connection.commit()


def _seed_business(client: DatabaseClient, database: str) -> None:
    projects, _fa_balances, _valuations, _pact_assets, _dm_project_invest, pledge_rows, currency_rows = _scenario_rows()
    q_database = _mysql_ident(database)
    with client._connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {q_database}.`zf_detail_2024` (
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
                CREATE TABLE IF NOT EXISTS {q_database}.`currency_report_duration` (
                  id1 varchar(255) PRIMARY KEY,
                  caldate date,
                  c_projectcode varchar(100),
                  c_projectname varchar(255),
                  f_assetshare decimal(24, 2)
                )
                """
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
            _ensure_report_period_tables(cursor)
            cursor.execute(_delete_sql(f"{q_database}.`zf_detail_2024`", "caldate", "projinnercode"), (*REPORT_DATES, f"{PROJECT_PREFIX}%"))
            cursor.execute(_delete_sql(f"{q_database}.`currency_report_duration`", "caldate", "c_projectcode"), (*REPORT_DATES, f"{PROJECT_PREFIX}%"))
            cursor.execute("DELETE FROM `assman_reg`.`ex_pledge_back` WHERE project_code LIKE %s", (f"{PROJECT_PREFIX}%",))
            cursor.executemany(
                f"INSERT INTO {q_database}.`zf_detail_2024` (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES (%s, %s, %s, %s, %s, %s)",
                projects,
            )
            cursor.executemany(
                f"INSERT INTO {q_database}.`currency_report_duration` (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES (%s, %s, %s, %s, %s)",
                currency_rows,
            )
            cursor.executemany(
                "INSERT INTO `assman_reg`.`ex_pledge_back` (project_code, subcode, buyback_money, expenses) VALUES (%s, %s, %s, %s)",
                pledge_rows,
            )
        connection.commit()


def _ensure_report_period_tables(cursor) -> None:
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
            f"DELETE FROM `currency_report_24`.`{table}` WHERE caldate IN ({','.join(['%s'] * len(REPORT_DATES))})",
            REPORT_DATES,
        )
        cursor.executemany(
            f"INSERT INTO `currency_report_24`.`{table}` (caldate) VALUES (%s)",
            [(day,) for day in REPORT_DATES],
        )


def _delete_previous_generated_history(config_path: Path) -> None:
    db_path = db_path_for_config(config_path)
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            DELETE FROM history_runs
            WHERE kind = 'reconcile'
              AND (
                payload LIKE ?
                OR payload LIKE ?
              )
            """,
            (f'%"executor_id": "{HISTORY_EXECUTOR_ID}"%', f"%{PROJECT_PREFIX}%"),
        )


def _promote_history_specific_reasons(config_path: Path) -> None:
    db_path = db_path_for_config(config_path)
    if not db_path.exists():
        return
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, payload
            FROM history_runs
            WHERE kind = 'reconcile'
              AND payload LIKE ?
            """,
            (f"%{PROJECT_PREFIX}%",),
        ).fetchall()
        for row in rows:
            payload = json.loads(row["payload"])
            changed = False
            for result in payload.get("results", []):
                specific_reason = _result_specific_reason(result)
                if specific_reason and result.get("specific_reason") != specific_reason:
                    result["specific_reason"] = specific_reason
                    changed = True
            if changed:
                payload["reason_counts"] = _reason_counts(payload.get("results", []))
                payload["status_counts"] = _status_counts(payload.get("results", []))
                connection.execute(
                    "UPDATE history_runs SET payload = ? WHERE kind = 'reconcile' AND id = ?",
                    (json.dumps(payload, ensure_ascii=False, sort_keys=True), row["id"]),
                )


def _result_specific_reason(result: dict) -> str:
    reasons = []
    for detail in result.get("details", []):
        data = detail.get("data", {})
        reason = str(data.get("specific_reason") or "").strip()
        if reason:
            reasons.append(reason)
    return reasons[-1] if reasons else ""


def _reason_counts(results: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        key = str(result.get("difference_reason", ""))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _status_counts(results: Iterable[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        key = str(result.get("match_status", ""))
        counts[key] = counts.get(key, 0) + 1
    return counts


def _run_reconcile_history(config_path: Path) -> None:
    router = ApiRouter(config_path=config_path)
    current_user = {
        "id": HISTORY_EXECUTOR_ID,
        "username": "admin",
        "display_name": "管理员",
    }
    for day in REPORT_DATES:
        status, payload = router.handle(
            "POST",
            "/api/run",
            {"date": day, "max_combination_rows": 50},
            current_user=current_user,
        )
        if status != 200:
            raise RuntimeError(f"run {day} failed: {payload}")
        print(f"{day}: {len(payload.get('results', []))} results")


def _print_verification(config: AppConfig, config_path: Path) -> None:
    client = DatabaseClient(config.business)
    table = qualified_name(config.business, "zf_detail_2024")
    rows = client.fetch_all(
        f"""
        SELECT caldate, COUNT(*) AS count
        FROM {table}
        WHERE caldate IN ({','.join(['%s'] * len(REPORT_DATES))})
          AND projinnercode LIKE %s
        GROUP BY caldate
        ORDER BY caldate
        """,
        (*REPORT_DATES, f"{PROJECT_PREFIX}%"),
    )
    print("Seeded report rows:")
    for row in rows:
        print(f"  {row['caldate']}: {row['count']}")

    runs = [
        run
        for run in list_history_runs(config_path, "reconcile")
        if any(str(item.get("project_code") or "").startswith(PROJECT_PREFIX) for item in run.get("results", []))
    ]
    runs.sort(key=lambda item: (str(item.get("run_date") or ""), str(item.get("run_at") or ""), str(item.get("id") or "")), reverse=True)
    if not runs:
        print("Home stats verification: no generated history found")
        return

    latest = runs[0]
    latest_results = list(latest.get("results", []))
    status_counts: dict[str, int] = {}
    for result in latest_results:
        status = str(result.get("match_status") or "")
        status_counts[status] = status_counts.get(status, 0) + 1

    paid_in_projects = [
        str(result.get("project_code") or "")
        for result in latest_results
        if _matches_home_paid_in_reason(result)
    ]
    target_code_projects = [
        str(result.get("project_code") or "")
        for result in latest_results
        if _matches_home_target_code_reason(result)
    ]
    frequency_periods: dict[str, set[str]] = {}
    for run in runs[:12]:
        for result in run.get("results", []):
            code = str(result.get("project_code") or "")
            if not code.startswith(PROJECT_PREFIX):
                continue
            frequency_periods.setdefault(code, set()).add(str(run.get("run_date") or ""))
    frequency_items = sorted((code, len(periods)) for code, periods in frequency_periods.items() if len(periods) >= 2)

    print("Home stats verification:")
    print(f"  latest: {latest.get('run_date')} total={len(latest_results)} status={status_counts}")
    print(f"  paid-in mismatch projects: {paid_in_projects}")
    print(f"  target-code mismatch projects: {target_code_projects}")
    print(f"  high-frequency projects: {frequency_items}")


def _matches_home_paid_in_reason(result: dict) -> bool:
    text = str(result.get("specific_reason") or "").replace(" ", "")
    return "4001与c1000存在差异" in text or "4001-c1000差额正好解释主差异" in text


def _matches_home_target_code_reason(result: dict) -> bool:
    text = str(result.get("specific_reason") or "").lower()
    return any(reason in text for reason in ("fa/am标的不一致", "fa与am标的不一致", "fa和am标的不一致"))


def _delete_sql(table: str, date_col: str, code_col: str) -> str:
    placeholders = ",".join(["%s"] * len(REPORT_DATES))
    return f"DELETE FROM {table} WHERE {date_col} IN ({placeholders}) AND {code_col} LIKE %s"


def _pg_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _mysql_ident(identifier: str) -> str:
    return "`" + identifier.replace("`", "``") + "`"


if __name__ == "__main__":
    main()
