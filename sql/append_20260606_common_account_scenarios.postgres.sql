-- 2026-06-06 自动对数专项回归场景数据。
-- 覆盖 3001.XX 共同类资产/负债、实收本金多次重复、单条命中、多条命中、候选不唯一。
-- 使用方式：powershell -ExecutionPolicy Bypass -File scripts\load-local-pg-20260606-common-account-scenarios.ps1

CREATE SCHEMA IF NOT EXISTS dws;
CREATE SCHEMA IF NOT EXISTS dm;
CREATE SCHEMA IF NOT EXISTS zgxg_zhbs;
CREATE SCHEMA IF NOT EXISTS currency_report_24;
CREATE SCHEMA IF NOT EXISTS assman_reg;

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

CREATE TABLE IF NOT EXISTS assman_reg.ex_pledge_back (
  project_code varchar,
  subcode varchar,
  buyback_money numeric,
  expenses numeric
);

BEGIN;

DELETE FROM dws.zf_detail_2024
WHERE caldate = DATE '2026-06-06' AND projinnercode LIKE '2026GX0606%';
DELETE FROM dws.fa_accountbalance_dws
WHERE d_balancedate = DATE '2026-06-06' AND c_projcode LIKE '2026GX0606%';
DELETE FROM dws.fa_valuationreport_dws
WHERE d_valuationdate = DATE '2026-06-06' AND c_projcode LIKE '2026GX0606%';
DELETE FROM dws.currency_report_duration
WHERE caldate = DATE '2026-06-06' AND c_projectcode LIKE '2026GX0606%';
DELETE FROM dws.ta_pact_detail_dws
WHERE d_cldate = DATE '2026-06-06' AND c_projcode LIKE '2026GX0606%';
DELETE FROM dws.am_pactasset_dws
WHERE d_cldate = DATE '2026-06-06' AND c_projcode LIKE '2026GX0606%';
DELETE FROM dws.am_projinvest_dws
WHERE d_cldate = DATE '2026-06-06' AND c_projcode LIKE '2026GX0606%';
DELETE FROM dm.ta_pact_survamt_day_zgxg_dm
WHERE tpm_date = DATE '2026-06-06' AND tpm_tcmpcode LIKE '2026GX0606%';
DELETE FROM dm.fa_security_balance_zgxg_dm
WHERE sbm_cacldate = DATE '2026-06-06' AND sbm_projcode LIKE '2026GX0606%';
DELETE FROM dm.am_projinvest_zgxg_dm
WHERE pin_cldate = DATE '2026-06-06' AND pin_projcode LIKE '2026GX0606%';
DELETE FROM dm.am_projinvest_spv_zgxg_dm
WHERE svd_cldate = DATE '2026-06-06' AND svd_projcode LIKE '2026GX0606%';
DELETE FROM zgxg_zhbs.ccqxx
WHERE pjdw_projcode LIKE '2026GX0606%';
DELETE FROM assman_reg.ex_pledge_back
WHERE project_code LIKE '2026GX0606%';

-- A. 资产缺失：3001.XX 正数应收账款_共同类单条命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060601', '江苏信托-苏银短融应收款集合资金信托计划', 118000000.00, 120000000.00, 30000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060601', DATE '2026-06-06', '4001', '实收信托', 30000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060601', 'JS060601', DATE '2026-06-06', '0004', '资产合计', 120000000.00),
('2026GX060601', 'JS060601', DATE '2026-06-06', '1002.01.01.01.4301015519106601', '招商银行南京分行托管户活期存款', 116000000.00),
('2026GX060601', 'JS060601', DATE '2026-06-06', '3001.01', '应收证券清算款-银行间', 2000000.00);

-- B. 资产缺失：3001.XX 正数与债券资产多条组合命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060602', '江苏信托-江南稳享债券应收组合资金信托计划', 196500000.00, 200000000.00, 50000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060602', DATE '2026-06-06', '4001', '实收信托', 50000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060602', 'JS060602', DATE '2026-06-06', '0004', '资产合计', 200000000.00),
('2026GX060602', 'JS060602', DATE '2026-06-06', '1002.01.01.01.4301015519106602', '交通银行江苏省分行托管户活期存款', 111500000.00),
('2026GX060602', 'JS060602', DATE '2026-06-06', '1101.02.08.01.ZQ26060601', '24南京地铁MTN0066', 85000000.00),
('2026GX060602', 'JS060602', DATE '2026-06-06', '1101.02.08.01.ZQ26060602', '25江北新区PPN0066', 2100000.00),
('2026GX060602', 'JS060602', DATE '2026-06-06', '3001.01', '应收债券清算款-上清所', 1400000.00);

-- C. 资产重复：3001.XX 正数应收账款_共同类单条命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060603', '江苏信托-产业园应收款重复验证集合资金信托计划', 151500000.00, 150000000.00, 40000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060603', DATE '2026-06-06', '4001', '实收信托', 40000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060603', 'JS060603', DATE '2026-06-06', '0004', '资产合计', 150000000.00),
('2026GX060603', 'JS060603', DATE '2026-06-06', '1002.01.01.01.4301015519106603', '中信银行南京河西支行托管户活期存款', 148500000.00),
('2026GX060603', 'JS060603', DATE '2026-06-06', '3001.02', '应收申购款-产业园项目', 1500000.00);

-- D. 负债权益缺失：3001.XX 负数应付账款_共同类单条命中，按绝对值计算。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060604', '江苏信托-共同类应付款单项验证集合资金信托计划', 100000000.00, 99200000.00, 25000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060604', DATE '2026-06-06', '4001', '实收信托', 25000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060604', 'JS060604', DATE '2026-06-06', '0004', '资产合计', 100000000.00),
('2026GX060604', 'JS060604', DATE '2026-06-06', '3001.02', '应付证券清算款-银行间', -800000.00);

-- E. 负债权益重复：3001.XX 负数与费用科目多条组合命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060605', '江苏信托-共同类应付款组合验证集合资金信托计划', 180000000.00, 181200000.00, 60000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060605', DATE '2026-06-06', '4001', '实收信托', 60000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060605', 'JS060605', DATE '2026-06-06', '0004', '资产合计', 180000000.00),
('2026GX060605', 'JS060605', DATE '2026-06-06', '3001.03', '应付清算款-交易所', -700000.00),
('2026GX060605', 'JS060605', DATE '2026-06-06', '2203.02.01.01.FEE6605', '应付托管运营费用-组合项目', 500000.00);

-- F. 实收本金重复：c1000 为 FA4001 的 4 倍，识别重复计入 3 次。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060606', '江苏信托-实收本金多次重复验证集合资金信托计划', 210000000.00, 300000000.00, 120000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060606', DATE '2026-06-06', '4001', '实收信托', 30000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060606', 'JS060606', DATE '2026-06-06', '0004', '资产合计', 210000000.00),
('2026GX060606', 'JS060606', DATE '2026-06-06', '1002.01.01.01.4301015519106606', '中国银行江苏省分行托管户活期存款', 210000000.00);

-- G. 资产缺失候选不唯一：两组资产端候选均可解释 asset_gap。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060607', '江苏信托-资产候选不唯一验证集合资金信托计划', 249000000.00, 250000000.00, 80000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060607', DATE '2026-06-06', '4001', '实收信托', 80000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060607', 'JS060607', DATE '2026-06-06', '0004', '资产合计', 250000000.00),
('2026GX060607', 'JS060607', DATE '2026-06-06', '1002.01.01.01.4301015519106607', '宁波银行南京分行托管户活期存款', 600000.00),
('2026GX060607', 'JS060607', DATE '2026-06-06', '1101.02.05.01.ZQ26060607A', '24苏州高新MTN0066A', 500000.00),
('2026GX060607', 'JS060607', DATE '2026-06-06', '1101.02.05.01.ZQ26060607B', '25南京交通债0066B', 500000.00),
('2026GX060607', 'JS060607', DATE '2026-06-06', '3001.01', '应收证券清算款-候选组', 400000.00);

-- H. 负债权益候选不唯一：两组非 1 候选均可解释主差异。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060608', '江苏信托-负债候选不唯一验证集合资金信托计划', 160000000.00, 159000000.00, 50000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060608', DATE '2026-06-06', '4001', '实收信托', 50000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060608', 'JS060608', DATE '2026-06-06', '0004', '资产合计', 160000000.00),
('2026GX060608', 'JS060608', DATE '2026-06-06', '3001.02', '应付证券清算款-候选组', -400000.00),
('2026GX060608', 'JS060608', DATE '2026-06-06', '2203.02.01.01.FEE6608', '应付管理人报酬-候选组', 600000.00),
('2026GX060608', 'JS060608', DATE '2026-06-06', '2209.01.01.01.COST6608', '应付托管费-候选组', 500000.00),
('2026GX060608', 'JS060608', DATE '2026-06-06', '2221.01.01.01.TAX6608', '应交增值税-候选组', 500000.00);

-- I. 实收本金重复：单次重复仍可识别。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060609', '江苏信托-实收本金单次重复验证集合资金信托计划', 120000000.00, 140000000.00, 40000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060609', DATE '2026-06-06', '4001', '实收信托', 20000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060609', 'JS060609', DATE '2026-06-06', '0004', '资产合计', 120000000.00),
('2026GX060609', 'JS060609', DATE '2026-06-06', '1002.01.01.01.4301015519106609', '浦发银行南京分行托管户活期存款', 120000000.00);

-- J. 实收本金差异：c1000 不是 FA4001 的整数倍，不误判为实收本金重复。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-06', '2026GX060610', '江苏信托-实收本金非整数倍验证集合资金信托计划', 130000000.00, 145000000.00, 35000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026GX060610', DATE '2026-06-06', '4001', '实收信托', 20000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026GX060610', 'JS060610', DATE '2026-06-06', '0004', '资产合计', 130000000.00),
('2026GX060610', 'JS060610', DATE '2026-06-06', '1002.01.01.01.4301015519106610', '民生银行南京分行托管户活期存款', 130000000.00);

INSERT INTO dws.currency_report_duration
SELECT 'CRD-20260606-' || projinnercode, caldate, projinnercode, projname, c1000
FROM dws.zf_detail_2024
WHERE caldate = DATE '2026-06-06'
  AND projinnercode LIKE '2026GX0606%';

ANALYZE dws.zf_detail_2024;
ANALYZE dws.fa_accountbalance_dws;
ANALYZE dws.fa_valuationreport_dws;
ANALYZE dws.currency_report_duration;

COMMIT;
