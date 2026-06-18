-- Append generated performance test data after running seed_auto_check_test.postgres.sql.
-- It keeps the hand-written sample projects and refreshes only project codes beginning with PERF.

ALTER TABLE dws.fa_valuationreport_dws
  ADD COLUMN IF NOT EXISTS c_projcode varchar;

DELETE FROM dws.am_pactasset_dws WHERE c_projcode LIKE 'PERF%';
DELETE FROM dws.am_projinvest_dws WHERE c_projcode LIKE 'PERF%';
DELETE FROM dws.fa_valuationreport_dws WHERE c_projcode LIKE 'PERF%';
DELETE FROM dws.fa_accountbalance_dws WHERE c_projcode LIKE 'PERF%';
DELETE FROM dws.currency_report_duration WHERE c_projectcode LIKE 'PERF%';
DELETE FROM dws.zf_detail_2024 WHERE projinnercode LIKE 'PERF%';

DROP TABLE IF EXISTS perf_projects;

CREATE TEMP TABLE perf_projects AS
WITH generated AS (
  SELECT
    series_no,
    'PERF' || lpad(series_no::text, 6, '0') AS project_code,
    '华鑫信托-' ||
      CASE series_no % 6
        WHEN 0 THEN '恒盈现金管理'
        WHEN 1 THEN '聚鑫精选债券'
        WHEN 2 THEN '稳健财富传承'
        WHEN 3 THEN '嘉和甄选债券'
        WHEN 4 THEN '中债优选投资'
        ELSE '星耀资产配置'
      END ||
      series_no::text || '号集合资金信托计划' AS project_name,
    CASE
      WHEN series_no % 10 IN (0, 1, 2) THEN 'asset_missing'
      WHEN series_no % 10 IN (3, 4, 5) THEN 'asset_duplicate'
      WHEN series_no % 10 IN (6, 7) THEN 'received_trust'
      WHEN series_no % 10 = 8 THEN 'liability_equity'
      ELSE 'unknown'
    END AS reason_bucket,
    round(100000000::numeric + series_no * 10000::numeric + (series_no % 97) * 123.45::numeric, 2) AS asset_base,
    round(5000::numeric + (series_no % 173) * 37.29::numeric, 2) AS gap,
    round(20000000::numeric + series_no * 300::numeric + (series_no % 37) * 11.11::numeric, 2) AS trust_base
  FROM generate_series(1, 1500) AS series_no
),
calculated AS (
  SELECT
    *,
    CASE
      WHEN reason_bucket = 'asset_missing' THEN -gap
      WHEN reason_bucket = 'liability_equity' AND series_no % 4 = 0 THEN -gap
      ELSE gap
    END AS main_diff,
    CASE
      WHEN reason_bucket = 'asset_missing' THEN asset_base + gap
      WHEN reason_bucket = 'asset_duplicate' THEN asset_base
      ELSE asset_base
    END AS valuation_asset_total,
    CASE
      WHEN reason_bucket = 'asset_duplicate' THEN asset_base + gap
      ELSE asset_base
    END AS zf_asset_total
  FROM generated
)
SELECT
  *,
  zf_asset_total - main_diff AS liability_equity_total,
  trust_base AS c1000_balance,
  CASE
    WHEN reason_bucket = 'received_trust' THEN trust_base + main_diff
    ELSE trust_base
  END AS fa4001_balance,
  lpad((240000 + series_no)::text, 6, '0') AS stock_tail,
  'PR' || lpad(series_no::text, 5, '0') AS asset_code
FROM calculated;

INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000)
SELECT
  '2026-04-30',
  project_code,
  project_name,
  zf_asset_total,
  liability_equity_total,
  c1000_balance
FROM perf_projects;

INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare)
SELECT
  'CRD-202604-' || project_code,
  '2026-04-30',
  project_code,
  project_name,
  c1000_balance
FROM perf_projects;

INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance)
SELECT project_code, '2026-04-30', '4001', '实收信托', fa4001_balance
FROM perf_projects;

INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue)
SELECT project_code, asset_code, '2026-04-30', '0004', '资产合计', valuation_asset_total
FROM perf_projects;

-- Asset missing/duplicate projects: one matching 1-prefix leaf asset plus filler positions.
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue)
SELECT
  project_code,
  asset_code,
  '2026-04-30',
  '1101.02.15.01.' || stock_tail,
  CASE series_no % 5
    WHEN 0 THEN '23苏华04'
    WHEN 1 THEN 'G26资控1'
    WHEN 2 THEN '23淮投02'
    WHEN 3 THEN '26冀控K1'
    ELSE '23苏进02'
  END,
  gap
FROM perf_projects
WHERE reason_bucket IN ('asset_missing', 'asset_duplicate');

INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue)
SELECT
  p.project_code,
  p.asset_code,
  '2026-04-30',
  '1101.02.1C.01.' || lpad((300000 + p.series_no * 20 + filler_no)::text, 6, '0'),
  '组合持仓' || filler_no::text,
  round(1000::numeric + filler_no * 17.13::numeric + (p.series_no % 19) * 9.97::numeric, 2)
FROM perf_projects p
CROSS JOIN generate_series(1, 12) AS filler_no
WHERE p.reason_bucket IN ('asset_missing', 'asset_duplicate');

INSERT INTO dws.am_pactasset_dws (c_projcode, d_cldate, c_udlyasset, c_stockcode)
SELECT
  project_code,
  '2026-04-30',
  CASE series_no % 5
    WHEN 0 THEN '23苏华04'
    WHEN 1 THEN 'G26资控1'
    WHEN 2 THEN '23淮投02'
    WHEN 3 THEN '26冀控K1'
    ELSE '23苏进02'
  END,
  CASE
    WHEN series_no % 4 = 0 THEN lpad((260000 + series_no)::text, 6, '0')
    ELSE stock_tail
  END
FROM perf_projects
WHERE reason_bucket IN ('asset_missing', 'asset_duplicate');

-- Liability/equity projects: c1000 is correct, non-1 valuation rows explain the gap.
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue)
SELECT project_code, asset_code, '2026-04-30', '2001.01', '应付管理费', abs(main_diff)
FROM perf_projects
WHERE reason_bucket = 'liability_equity'
  AND series_no % 2 = 0;

INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue)
SELECT project_code, asset_code, '2026-04-30', '2203.01', '应付托管费', round(abs(main_diff) * 0.4, 2)
FROM perf_projects
WHERE reason_bucket = 'liability_equity'
  AND series_no % 2 = 1;

INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue)
SELECT project_code, asset_code, '2026-04-30', '2203.01', '应付托管费', abs(main_diff) - round(abs(main_diff) * 0.4, 2)
FROM perf_projects
WHERE reason_bucket = 'liability_equity'
  AND series_no % 2 = 1;

-- Unknown projects: more than the combination limit, but no direct or grouped match.
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue)
SELECT
  p.project_code,
  p.asset_code,
  '2026-04-30',
  '2' || lpad((100 + unknown_no)::text, 3, '0') || '.01',
  '待排查非资产科目' || unknown_no::text,
  round(100::numeric + unknown_no * 13.11::numeric + (p.series_no % 17) * 3.37::numeric, 2)
FROM perf_projects p
CROSS JOIN generate_series(1, 25) AS unknown_no
WHERE p.reason_bucket = 'unknown';

ANALYZE dws.zf_detail_2024;
ANALYZE dws.currency_report_duration;
ANALYZE dws.fa_accountbalance_dws;
ANALYZE dws.fa_valuationreport_dws;
ANALYZE dws.am_pactasset_dws;
ANALYZE dws.am_projinvest_dws;

SELECT
  reason_bucket,
  count(*) AS project_count
FROM perf_projects
GROUP BY reason_bucket
ORDER BY reason_bucket;
