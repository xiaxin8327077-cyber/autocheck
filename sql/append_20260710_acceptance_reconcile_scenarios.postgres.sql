-- 2026-07-10 acceptance data for automatic reconciliation.
-- This script is idempotent. It reloads only AC20260710* rows and one AC20260709* date-boundary row.
-- Current storage-v2 reconciliation uses per-table data source settings; these tables may all live in one PostgreSQL test schema.

CREATE SCHEMA IF NOT EXISTS dws;
CREATE SCHEMA IF NOT EXISTS dm;
CREATE SCHEMA IF NOT EXISTS zgxg_zhbs;
CREATE SCHEMA IF NOT EXISTS currency_report_24;
CREATE SCHEMA IF NOT EXISTS ass_man_reg;

CREATE TABLE IF NOT EXISTS dws.zf_detail_2024 (
  caldate date NOT NULL,
  projinnercode varchar NOT NULL,
  projname varchar NOT NULL,
  a0001 numeric NOT NULL,
  d0000 numeric NOT NULL,
  c1000 numeric NOT NULL
);

CREATE TABLE IF NOT EXISTS dws.currency_report_duration (
  id1 varchar PRIMARY KEY,
  caldate date,
  c_projectcode varchar,
  c_projectname varchar,
  f_assetshare numeric
);

CREATE TABLE IF NOT EXISTS dws.fa_accountbalance_dws (
  c_projcode varchar,
  d_balancedate date,
  c_accountcode varchar,
  c_accountname varchar,
  f_balance numeric
);

CREATE TABLE IF NOT EXISTS dws.fa_valuationreport_dws (
  c_projcode varchar,
  c_assetcode varchar,
  d_valuationdate date,
  c_accountcode varchar,
  c_accountname varchar,
  f_marketvalue numeric
);

CREATE TABLE IF NOT EXISTS dws.ta_pact_detail_dws (
  d_cldate date,
  c_projcode varchar,
  c_pactid varchar,
  f_shareamt numeric,
  f_alltincom numeric
);

CREATE TABLE IF NOT EXISTS dws.am_pactasset_dws (
  c_projcode varchar,
  d_cldate date,
  c_pactid varchar,
  c_udlyasset varchar,
  c_stockcode varchar,
  c_spv_type varchar,
  c_assettype varchar
);

ALTER TABLE dws.am_pactasset_dws ADD COLUMN IF NOT EXISTS c_spv_type varchar;
ALTER TABLE dws.am_pactasset_dws ADD COLUMN IF NOT EXISTS c_assettype varchar;

CREATE TABLE IF NOT EXISTS dws.am_projinvest_dws (
  c_projcode varchar,
  d_cldate date,
  c_pactid varchar,
  f_acbalance numeric
);

CREATE TABLE IF NOT EXISTS dm.ta_pact_survamt_day_zgxg_dm (
  tpm_date date,
  tpm_tcmpcode varchar,
  tpm_pactid varchar,
  tpm_clientname varchar,
  tpm_clientkind_tusp varchar,
  tpm_clientkindex varchar,
  tpm_spvtype varchar,
  tpm_htincome numeric,
  tpm_shareamt numeric
);

CREATE TABLE IF NOT EXISTS dm.fa_security_balance_zgxg_dm (
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
);

CREATE TABLE IF NOT EXISTS dm.am_projinvest_zgxg_dm (
  pin_projcode varchar,
  pin_cldate date,
  pin_mpactid varchar,
  pin_acbalance numeric,
  pin_gqtype_h varchar
);

CREATE TABLE IF NOT EXISTS dm.am_projinvest_spv_zgxg_dm (
  svd_projcode varchar,
  svd_cldate date,
  svd_mpactid varchar,
  svd_balamoney_cost numeric,
  svd_balamoney_inte numeric,
  svd_balamoney_fair numeric,
  svd_assettype varchar
);

CREATE TABLE IF NOT EXISTS zgxg_zhbs.ccqxx (
  pjdw_projcode varchar,
  pin_mpactid varchar,
  pin_acbalance numeric
);

CREATE TABLE IF NOT EXISTS currency_report_24.currency_detail_project_2_1_2 (caldate date);
CREATE TABLE IF NOT EXISTS currency_report_24.currency_detail_project_2_1_4 (caldate date);
CREATE TABLE IF NOT EXISTS currency_report_24.currency_detail_project_2_1_5 (caldate date);
CREATE TABLE IF NOT EXISTS currency_report_24.currency_detail_project_2_1_5_2 (caldate date);
CREATE TABLE IF NOT EXISTS currency_report_24.currency_detail_project_2_1_6 (caldate date);
CREATE TABLE IF NOT EXISTS currency_report_24.currency_detail_project_2_1_8 (caldate date);
CREATE TABLE IF NOT EXISTS currency_report_24.currency_detail_project_2_1_9 (caldate date);

CREATE TABLE IF NOT EXISTS ass_man_reg.ex_pledge_back (
  project_code varchar,
  subcode varchar,
  buyback_money numeric,
  expenses numeric
);

BEGIN;

DELETE FROM dws.zf_detail_2024
WHERE (caldate = DATE '2026-07-10' AND projinnercode LIKE 'AC20260710%')
   OR (caldate = DATE '2026-07-09' AND projinnercode LIKE 'AC20260709%');
DELETE FROM dws.fa_accountbalance_dws
WHERE (d_balancedate = DATE '2026-07-10' AND c_projcode LIKE 'AC20260710%')
   OR (d_balancedate = DATE '2026-07-09' AND c_projcode LIKE 'AC20260709%');
DELETE FROM dws.fa_valuationreport_dws
WHERE (d_valuationdate = DATE '2026-07-10' AND c_projcode LIKE 'AC20260710%')
   OR (d_valuationdate = DATE '2026-07-09' AND c_projcode LIKE 'AC20260709%');
DELETE FROM dws.currency_report_duration
WHERE (caldate = DATE '2026-07-10' AND c_projectcode LIKE 'AC20260710%')
   OR (caldate = DATE '2026-07-09' AND c_projectcode LIKE 'AC20260709%');
DELETE FROM dws.ta_pact_detail_dws WHERE d_cldate = DATE '2026-07-10' AND c_projcode LIKE 'AC20260710%';
DELETE FROM dws.am_pactasset_dws WHERE d_cldate = DATE '2026-07-10' AND c_projcode LIKE 'AC20260710%';
DELETE FROM dws.am_projinvest_dws WHERE d_cldate = DATE '2026-07-10' AND c_projcode LIKE 'AC20260710%';
DELETE FROM dm.ta_pact_survamt_day_zgxg_dm WHERE tpm_date = DATE '2026-07-10' AND tpm_tcmpcode LIKE 'AC20260710%';
DELETE FROM dm.fa_security_balance_zgxg_dm WHERE sbm_cacldate = DATE '2026-07-10' AND sbm_projcode LIKE 'AC20260710%';
DELETE FROM dm.am_projinvest_zgxg_dm WHERE pin_cldate = DATE '2026-07-10' AND pin_projcode LIKE 'AC20260710%';
DELETE FROM dm.am_projinvest_spv_zgxg_dm WHERE svd_cldate = DATE '2026-07-10' AND svd_projcode LIKE 'AC20260710%';
DELETE FROM zgxg_zhbs.ccqxx WHERE pjdw_projcode LIKE 'AC20260710%';
DELETE FROM ass_man_reg.ex_pledge_back WHERE project_code LIKE 'AC20260710%';
INSERT INTO currency_report_24.currency_detail_project_2_1_2
SELECT DATE '2026-07-10'
WHERE NOT EXISTS (SELECT 1 FROM currency_report_24.currency_detail_project_2_1_2 WHERE caldate = DATE '2026-07-10');
INSERT INTO currency_report_24.currency_detail_project_2_1_4
SELECT DATE '2026-07-10'
WHERE NOT EXISTS (SELECT 1 FROM currency_report_24.currency_detail_project_2_1_4 WHERE caldate = DATE '2026-07-10');
INSERT INTO currency_report_24.currency_detail_project_2_1_5
SELECT DATE '2026-07-10'
WHERE NOT EXISTS (SELECT 1 FROM currency_report_24.currency_detail_project_2_1_5 WHERE caldate = DATE '2026-07-10');
INSERT INTO currency_report_24.currency_detail_project_2_1_5_2
SELECT DATE '2026-07-10'
WHERE NOT EXISTS (SELECT 1 FROM currency_report_24.currency_detail_project_2_1_5_2 WHERE caldate = DATE '2026-07-10');
INSERT INTO currency_report_24.currency_detail_project_2_1_6
SELECT DATE '2026-07-10'
WHERE NOT EXISTS (SELECT 1 FROM currency_report_24.currency_detail_project_2_1_6 WHERE caldate = DATE '2026-07-10');
INSERT INTO currency_report_24.currency_detail_project_2_1_8
SELECT DATE '2026-07-10'
WHERE NOT EXISTS (SELECT 1 FROM currency_report_24.currency_detail_project_2_1_8 WHERE caldate = DATE '2026-07-10');
INSERT INTO currency_report_24.currency_detail_project_2_1_9
SELECT DATE '2026-07-10'
WHERE NOT EXISTS (SELECT 1 FROM currency_report_24.currency_detail_project_2_1_9 WHERE caldate = DATE '2026-07-10');

-- 1. Perfect match: should be read as source data, but should not appear in result rows because a0001=d0000.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-07-10', 'AC20260710MATCH01', '验收-完全匹配-不应输出差异', 1000000.00, 1000000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260710MATCH01', DATE '2026-07-10', '4001', '实收信托', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260710MATCH01', 'ACASSET7101', DATE '2026-07-10', '0004', '资产合计', 1000000.00);

-- 2. Amount difference: asset side is correct; FA 4001 and c1000 explain the main difference.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-07-10', 'AC20260710AMOUNT01', '验收-金额差异-实收本金差异', 1000000.00, 980000.00, 280000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260710AMOUNT01', DATE '2026-07-10', '4001', '实收信托', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260710AMOUNT01', 'ACASSET7102', DATE '2026-07-10', '0004', '资产合计', 1000000.00);

-- 3. Business missing: source report row exists, but FA valuation 0004 is intentionally absent.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-07-10', 'AC20260710BIZMISS01', '验收-业务缺失-缺估值0004', 1000000.00, 900000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260710BIZMISS01', DATE '2026-07-10', '4001', '实收信托', 300000.00);

-- 4. Asset missing: zf_detail asset total is lower than FA valuation 0004, and one asset candidate explains the gap.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-07-10', 'AC20260710ASSETMISS01', '验收-资产缺失-单科目命中', 900000.00, 1000000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260710ASSETMISS01', DATE '2026-07-10', '4001', '实收信托', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260710ASSETMISS01', 'ACASSET7104', DATE '2026-07-10', '0004', '资产合计', 1000000.00),
('AC20260710ASSETMISS01', 'ACASSET7104', DATE '2026-07-10', '1501.01.02.01.BOND7104', '验收债券7104', 100000.00);

-- 5. Ambiguous candidates: two 60k+40k combinations can explain the same 100k asset gap.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-07-10', 'AC20260710AMB01', '验收-候选不唯一-多组合命中', 900000.00, 1000000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260710AMB01', DATE '2026-07-10', '4001', '实收信托', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260710AMB01', 'ACASSET7105', DATE '2026-07-10', '0004', '资产合计', 1000000.00),
('AC20260710AMB01', 'ACASSET7105', DATE '2026-07-10', '1501.01.02.01.BOND7105A', '验收候选A', 60000.00),
('AC20260710AMB01', 'ACASSET7105', DATE '2026-07-10', '1501.01.02.01.BOND7105B', '验收候选B', 40000.00),
('AC20260710AMB01', 'ACASSET7105', DATE '2026-07-10', '1501.01.02.01.BOND7105C', '验收候选C', 60000.00),
('AC20260710AMB01', 'ACASSET7105', DATE '2026-07-10', '1501.01.02.01.BOND7105D', '验收候选D', 40000.00);

-- 6. Date boundary: this 2026-07-09 row must not appear when running report date 2026-07-10.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-07-09', 'AC20260709DATE01', '验收-日期边界-非0710数据', 500000.00, 400000.00, 100000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260709DATE01', DATE '2026-07-09', '4001', '实收信托', 100000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260709DATE01', 'ACASSET7901', DATE '2026-07-09', '0004', '资产合计', 500000.00);

-- 7. Null/empty value tolerance: account name is NULL and should not break result generation.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-07-10', 'AC20260710NULL01', '验收-空值-估值科目名为空', 940000.00, 1000000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260710NULL01', DATE '2026-07-10', '4001', '实收信托', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260710NULL01', 'ACASSET7107', DATE '2026-07-10', '0004', '资产合计', 1000000.00),
('AC20260710NULL01', 'ACASSET7107', DATE '2026-07-10', '1501.01.02.01.BOND7107', NULL, 60000.00);

-- 8. Duplicate record: duplicate zf_detail rows with the same project code validate repeat-row handling.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-07-10', 'AC20260710DUP01', '验收-重复记录-第一行', 1000000.00, 920000.00, 300000.00),
(DATE '2026-07-10', 'AC20260710DUP01', '验收-重复记录-第二行', 1000000.00, 920000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260710DUP01', DATE '2026-07-10', '4001', '实收信托', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260710DUP01', 'ACASSET7108', DATE '2026-07-10', '0004', '资产合计', 1000000.00),
('AC20260710DUP01', 'ACASSET7108', DATE '2026-07-10', '2001.01', '验收应付管理费', 80000.00);

INSERT INTO dws.currency_report_duration
SELECT 'CRD-20260710-' || projinnercode || '-' || row_number() OVER (PARTITION BY projinnercode ORDER BY projname),
       caldate,
       projinnercode,
       projname,
       c1000
FROM dws.zf_detail_2024
WHERE caldate = DATE '2026-07-10'
  AND projinnercode LIKE 'AC20260710%';

ANALYZE dws.zf_detail_2024;
ANALYZE dws.fa_accountbalance_dws;
ANALYZE dws.fa_valuationreport_dws;
ANALYZE dws.currency_report_duration;

COMMIT;
