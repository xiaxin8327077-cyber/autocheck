-- 2026-06-14 ~ 2026-06-16 auto-check local PostgreSQL reconcile scenarios.
-- The script is idempotent: it deletes and reloads only project codes starting with AC20260614/15/16.

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
WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (projinnercode LIKE 'AC20260614%' OR projinnercode LIKE 'AC20260615%' OR projinnercode LIKE 'AC20260616%');
DELETE FROM dws.fa_accountbalance_dws
WHERE d_balancedate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (c_projcode LIKE 'AC20260614%' OR c_projcode LIKE 'AC20260615%' OR c_projcode LIKE 'AC20260616%');
DELETE FROM dws.fa_valuationreport_dws
WHERE d_valuationdate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (c_projcode LIKE 'AC20260614%' OR c_projcode LIKE 'AC20260615%' OR c_projcode LIKE 'AC20260616%');
DELETE FROM dws.currency_report_duration
WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (c_projectcode LIKE 'AC20260614%' OR c_projectcode LIKE 'AC20260615%' OR c_projectcode LIKE 'AC20260616%');
DELETE FROM dws.ta_pact_detail_dws
WHERE d_cldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (c_projcode LIKE 'AC20260614%' OR c_projcode LIKE 'AC20260615%' OR c_projcode LIKE 'AC20260616%');
DELETE FROM dws.am_pactasset_dws
WHERE d_cldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (c_projcode LIKE 'AC20260614%' OR c_projcode LIKE 'AC20260615%' OR c_projcode LIKE 'AC20260616%');
DELETE FROM dws.am_projinvest_dws
WHERE d_cldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (c_projcode LIKE 'AC20260614%' OR c_projcode LIKE 'AC20260615%' OR c_projcode LIKE 'AC20260616%');
DELETE FROM dm.ta_pact_survamt_day_zgxg_dm
WHERE tpm_date IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (tpm_tcmpcode LIKE 'AC20260614%' OR tpm_tcmpcode LIKE 'AC20260615%' OR tpm_tcmpcode LIKE 'AC20260616%');
DELETE FROM dm.fa_security_balance_zgxg_dm
WHERE sbm_cacldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (sbm_projcode LIKE 'AC20260614%' OR sbm_projcode LIKE 'AC20260615%' OR sbm_projcode LIKE 'AC20260616%');
DELETE FROM dm.am_projinvest_zgxg_dm
WHERE pin_cldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (pin_projcode LIKE 'AC20260614%' OR pin_projcode LIKE 'AC20260615%' OR pin_projcode LIKE 'AC20260616%');
DELETE FROM dm.am_projinvest_spv_zgxg_dm
WHERE svd_cldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (svd_projcode LIKE 'AC20260614%' OR svd_projcode LIKE 'AC20260615%' OR svd_projcode LIKE 'AC20260616%');
DELETE FROM zgxg_zhbs.ccqxx
WHERE pjdw_projcode LIKE 'AC20260614%' OR pjdw_projcode LIKE 'AC20260615%' OR pjdw_projcode LIKE 'AC20260616%';
DELETE FROM ass_man_reg.ex_pledge_back
WHERE project_code LIKE 'AC20260614%' OR project_code LIKE 'AC20260615%' OR project_code LIKE 'AC20260616%';
DELETE FROM currency_report_24.currency_detail_project_2_1_2 WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16');
DELETE FROM currency_report_24.currency_detail_project_2_1_4 WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16');
DELETE FROM currency_report_24.currency_detail_project_2_1_5 WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16');
DELETE FROM currency_report_24.currency_detail_project_2_1_5_2 WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16');
DELETE FROM currency_report_24.currency_detail_project_2_1_6 WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16');
DELETE FROM currency_report_24.currency_detail_project_2_1_8 WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16');
DELETE FROM currency_report_24.currency_detail_project_2_1_9 WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16');

INSERT INTO currency_report_24.currency_detail_project_2_1_2 VALUES
(DATE '2026-06-14'), (DATE '2026-06-15'), (DATE '2026-06-16');
INSERT INTO currency_report_24.currency_detail_project_2_1_4 VALUES
(DATE '2026-06-14'), (DATE '2026-06-15'), (DATE '2026-06-16');
INSERT INTO currency_report_24.currency_detail_project_2_1_5 VALUES
(DATE '2026-06-14'), (DATE '2026-06-15'), (DATE '2026-06-16');
INSERT INTO currency_report_24.currency_detail_project_2_1_5_2 VALUES
(DATE '2026-06-14'), (DATE '2026-06-15'), (DATE '2026-06-16');
INSERT INTO currency_report_24.currency_detail_project_2_1_6 VALUES
(DATE '2026-06-14'), (DATE '2026-06-15'), (DATE '2026-06-16');
INSERT INTO currency_report_24.currency_detail_project_2_1_8 VALUES
(DATE '2026-06-14'), (DATE '2026-06-15'), (DATE '2026-06-16');
INSERT INTO currency_report_24.currency_detail_project_2_1_9 VALUES
(DATE '2026-06-14'), (DATE '2026-06-15'), (DATE '2026-06-16');

-- 2026-06-14: asset-side and unknown scenarios.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-14', 'AC20260614UNK01', '2026-06-14 unknown without valuation total', 1000000.00, 900000.00, 300000.00),
(DATE '2026-06-14', 'AC20260614AM01', '2026-06-14 asset missing single bond', 900000.00, 1000000.00, 300000.00),
(DATE '2026-06-14', 'AC20260614AD01', '2026-06-14 asset duplicate single bond', 1100000.00, 1000000.00, 300000.00),
(DATE '2026-06-14', 'AC20260614DIFF01', '2026-06-14 asset difference loan full match', 1050000.00, 1000000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260614UNK01', DATE '2026-06-14', '4001', 'received trust principal', 300000.00),
('AC20260614AM01', DATE '2026-06-14', '4001', 'received trust principal', 300000.00),
('AC20260614AD01', DATE '2026-06-14', '4001', 'received trust principal', 300000.00),
('AC20260614DIFF01', DATE '2026-06-14', '4001', 'received trust principal', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260614AM01', 'ACASSET1401', DATE '2026-06-14', '0004', 'asset total', 1000000.00),
('AC20260614AM01', 'ACASSET1401', DATE '2026-06-14', '1501.01.02.01.BOND1401', 'scenario bond 1401', 100000.00),
('AC20260614AD01', 'ACASSET1402', DATE '2026-06-14', '0004', 'asset total', 1000000.00),
('AC20260614AD01', 'ACASSET1402', DATE '2026-06-14', '1501.01.02.01.BOND1402', 'scenario bond 1402', 100000.00),
('AC20260614DIFF01', 'ACASSET1403', DATE '2026-06-14', '0004', 'asset total', 1000000.00),
('AC20260614DIFF01', 'ACASSET1403', DATE '2026-06-14', '1303.01.01.01.DK2026061401', 'scenario loan 1401', 100000.00);
INSERT INTO dm.am_projinvest_zgxg_dm VALUES
('AC20260614DIFF01', DATE '2026-06-14', 'DK2026061401', 150000.00, NULL);

-- 2026-06-15: received trust and liability/equity scenarios.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-15', 'AC20260615RTMISS01', '2026-06-15 received trust missing', 1000000.00, 900000.00, 0.00),
(DATE '2026-06-15', 'AC20260615RTDUP01', '2026-06-15 received trust duplicate', 1000000.00, 1100000.00, 200000.00),
(DATE '2026-06-15', 'AC20260615RTDIFF01', '2026-06-15 received trust difference', 1000000.00, 980000.00, 80000.00),
(DATE '2026-06-15', 'AC20260615LEMISS01', '2026-06-15 liability equity missing', 1000000.00, 900000.00, 300000.00),
(DATE '2026-06-15', 'AC20260615LEDUP01', '2026-06-15 liability equity duplicate', 1000000.00, 1100000.00, 300000.00),
(DATE '2026-06-15', 'AC20260615LEDIFF01', '2026-06-15 liability equity positive repo difference', 1000000.00, 900000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260615RTMISS01', DATE '2026-06-15', '4001', 'received trust principal', 100000.00),
('AC20260615RTDUP01', DATE '2026-06-15', '4001', 'received trust principal', 100000.00),
('AC20260615RTDIFF01', DATE '2026-06-15', '4001', 'received trust principal', 100000.00),
('AC20260615LEMISS01', DATE '2026-06-15', '4001', 'received trust principal', 300000.00),
('AC20260615LEDUP01', DATE '2026-06-15', '4001', 'received trust principal', 300000.00),
('AC20260615LEDIFF01', DATE '2026-06-15', '4001', 'received trust principal', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260615RTMISS01', 'ACASSET1501', DATE '2026-06-15', '0004', 'asset total', 1000000.00),
('AC20260615RTDUP01', 'ACASSET1502', DATE '2026-06-15', '0004', 'asset total', 1000000.00),
('AC20260615RTDIFF01', 'ACASSET1503', DATE '2026-06-15', '0004', 'asset total', 1000000.00),
('AC20260615LEMISS01', 'ACASSET1504', DATE '2026-06-15', '0004', 'asset total', 1000000.00),
('AC20260615LEMISS01', 'ACASSET1504', DATE '2026-06-15', '2001.01', 'scenario payable management fee', 100000.00),
('AC20260615LEDUP01', 'ACASSET1505', DATE '2026-06-15', '0004', 'asset total', 1000000.00),
('AC20260615LEDUP01', 'ACASSET1505', DATE '2026-06-15', '2001.02', 'scenario duplicated payable', 100000.00),
('AC20260615LEDIFF01', 'ACASSET1506', DATE '2026-06-15', '0004', 'asset total', 1000000.00),
('AC20260615LEDIFF01', 'ACASSET1506', DATE '2026-06-15', '2111.01.01.01.RP2026061501', 'scenario positive repo', 150000.00);
INSERT INTO ass_man_reg.ex_pledge_back VALUES
('AC20260615LEDIFF01', '8001501', 60000.00, 10000.00);

-- 2026-06-16: mixed, 3001 common account, ambiguous, and bond DM scenarios.
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-16', 'AC20260616MIX01', '2026-06-16 received trust plus liability', 1000000.00, 850000.00, 280000.00),
(DATE '2026-06-16', 'AC20260616COMA01', '2026-06-16 common receivable asset missing', 900000.00, 1000000.00, 300000.00),
(DATE '2026-06-16', 'AC20260616COMP01', '2026-06-16 common payable liability missing', 1000000.00, 920000.00, 300000.00),
(DATE '2026-06-16', 'AC20260616AMB01', '2026-06-16 asset missing ambiguous candidates', 900000.00, 1000000.00, 300000.00),
(DATE '2026-06-16', 'AC20260616BOND01', '2026-06-16 bond DM asset difference', 1050000.00, 1000000.00, 300000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('AC20260616MIX01', DATE '2026-06-16', '4001', 'received trust principal', 300000.00),
('AC20260616COMA01', DATE '2026-06-16', '4001', 'received trust principal', 300000.00),
('AC20260616COMP01', DATE '2026-06-16', '4001', 'received trust principal', 300000.00),
('AC20260616AMB01', DATE '2026-06-16', '4001', 'received trust principal', 300000.00),
('AC20260616BOND01', DATE '2026-06-16', '4001', 'received trust principal', 300000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('AC20260616MIX01', 'ACASSET1601', DATE '2026-06-16', '0004', 'asset total', 1000000.00),
('AC20260616MIX01', 'ACASSET1601', DATE '2026-06-16', '2203.02.01.01.FEE1601', 'scenario operation fee', 130000.00),
('AC20260616COMA01', 'ACASSET1602', DATE '2026-06-16', '0004', 'asset total', 1000000.00),
('AC20260616COMA01', 'ACASSET1602', DATE '2026-06-16', '3001.01', 'scenario common receivable', 100000.00),
('AC20260616COMP01', 'ACASSET1603', DATE '2026-06-16', '0004', 'asset total', 1000000.00),
('AC20260616COMP01', 'ACASSET1603', DATE '2026-06-16', '3001.02', 'scenario common payable', -80000.00),
('AC20260616AMB01', 'ACASSET1604', DATE '2026-06-16', '0004', 'asset total', 1000000.00),
('AC20260616AMB01', 'ACASSET1604', DATE '2026-06-16', '1501.01.02.01.BOND1604A', 'scenario ambiguous bond A', 60000.00),
('AC20260616AMB01', 'ACASSET1604', DATE '2026-06-16', '1501.01.02.01.BOND1604B', 'scenario ambiguous bond B', 40000.00),
('AC20260616AMB01', 'ACASSET1604', DATE '2026-06-16', '1501.01.02.01.BOND1604C', 'scenario ambiguous bond C', 60000.00),
('AC20260616AMB01', 'ACASSET1604', DATE '2026-06-16', '1501.01.02.01.BOND1604D', 'scenario ambiguous bond D', 40000.00),
('AC20260616BOND01', 'ACASSET1605', DATE '2026-06-16', '0004', 'asset total', 1000000.00),
('AC20260616BOND01', 'ACASSET1605', DATE '2026-06-16', '1501.01.02.01.BOND1605', 'scenario DM bond 1605', 100000.00);
INSERT INTO dm.fa_security_balance_zgxg_dm VALUES
('AC20260616BOND01', DATE '2026-06-16', 'BOND1605', 'scenario DM bond 1605', 150000.00, 0.00, 0.00, '01', NULL, NULL);

INSERT INTO dws.currency_report_duration
SELECT 'CRD-20260614-16-' || projinnercode, caldate, projinnercode, projname, c1000
FROM dws.zf_detail_2024
WHERE caldate IN (DATE '2026-06-14', DATE '2026-06-15', DATE '2026-06-16')
  AND (projinnercode LIKE 'AC20260614%' OR projinnercode LIKE 'AC20260615%' OR projinnercode LIKE 'AC20260616%');

ANALYZE dws.zf_detail_2024;
ANALYZE dws.fa_accountbalance_dws;
ANALYZE dws.fa_valuationreport_dws;
ANALYZE dws.currency_report_duration;

COMMIT;
