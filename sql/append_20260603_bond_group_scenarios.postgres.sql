-- 2026-06-03 自动对数专项回归场景数据。
-- 重点覆盖：全末级组合超限后的科目前四段分组组合、债券 DM 证券余额双边核对、
-- 多个债券主原因汇总展示、逆/正回购存续回购业务表金额核对。
-- 使用方式：powershell -ExecutionPolicy Bypass -File scripts\load-local-pg-20260603-bond-group-scenarios.ps1

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
WHERE caldate = DATE '2026-06-03' AND projinnercode LIKE '2026%0603%';
DELETE FROM dws.fa_accountbalance_dws
WHERE d_balancedate = DATE '2026-06-03' AND c_projcode LIKE '2026%0603%';
DELETE FROM dws.fa_valuationreport_dws
WHERE d_valuationdate = DATE '2026-06-03' AND c_projcode LIKE '2026%0603%';
DELETE FROM dws.currency_report_duration
WHERE caldate = DATE '2026-06-03' AND c_projectcode LIKE '2026%0603%';
DELETE FROM dws.ta_pact_detail_dws
WHERE d_cldate = DATE '2026-06-03' AND c_projcode LIKE '2026%0603%';
DELETE FROM dws.am_pactasset_dws
WHERE d_cldate = DATE '2026-06-03' AND c_projcode LIKE '2026%0603%';
DELETE FROM dws.am_projinvest_dws
WHERE d_cldate = DATE '2026-06-03' AND c_projcode LIKE '2026%0603%';
DELETE FROM dm.ta_pact_survamt_day_zgxg_dm
WHERE tpm_date = DATE '2026-06-03' AND tpm_tcmpcode LIKE '2026%0603%';
DELETE FROM dm.fa_security_balance_zgxg_dm
WHERE sbm_cacldate = DATE '2026-06-03' AND sbm_projcode LIKE '2026%0603%';
DELETE FROM dm.am_projinvest_zgxg_dm
WHERE pin_cldate = DATE '2026-06-03' AND pin_projcode LIKE '2026%0603%';
DELETE FROM dm.am_projinvest_spv_zgxg_dm
WHERE svd_cldate = DATE '2026-06-03' AND svd_projcode LIKE '2026%0603%';
DELETE FROM zgxg_zhbs.ccqxx
WHERE pjdw_projcode LIKE '2026%0603%';
DELETE FROM assman_reg.ex_pledge_back
WHERE project_code LIKE '2026%0603%';
DELETE FROM currency_report_24.currency_detail_project_2_1_2 WHERE caldate = DATE '2026-06-03';
DELETE FROM currency_report_24.currency_detail_project_2_1_4 WHERE caldate = DATE '2026-06-03';
DELETE FROM currency_report_24.currency_detail_project_2_1_5 WHERE caldate = DATE '2026-06-03';
DELETE FROM currency_report_24.currency_detail_project_2_1_5_2 WHERE caldate = DATE '2026-06-03';
DELETE FROM currency_report_24.currency_detail_project_2_1_6 WHERE caldate = DATE '2026-06-03';
DELETE FROM currency_report_24.currency_detail_project_2_1_8 WHERE caldate = DATE '2026-06-03';
DELETE FROM currency_report_24.currency_detail_project_2_1_9 WHERE caldate = DATE '2026-06-03';

INSERT INTO currency_report_24.currency_detail_project_2_1_2 VALUES (DATE '2026-06-03');
INSERT INTO currency_report_24.currency_detail_project_2_1_4 VALUES (DATE '2026-06-03');

-- A. 资产差异：债券本金分组仍超限，DM 证券余额差异完整解释，主原因汇总为“多个债券”。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-03', '2026ZQDM060301', '江苏信托-睿债优选1号集合资金信托计划', 612375000.00, 612500000.00, 180000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026ZQDM060301', DATE '2026-06-03', '4001', '实收信托', 180000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026ZQDM060301', 'JS060301', DATE '2026-06-03', '0004', '资产合计', 612500000.00),
('2026ZQDM060301', 'JS060301', DATE '2026-06-03', '1002.01.01.01.430101551910060301', '交通银行南京城中支行活期存款', 270227000.00);
INSERT INTO dws.fa_valuationreport_dws
SELECT
  '2026ZQDM060301',
  'JS060301',
  DATE '2026-06-03',
  '1101.02.03.01.ZQ260603' || lpad(gs::text, 3, '0'),
  CASE
    WHEN gs % 5 = 0 THEN '25苏交控MTN00' || gs::text
    WHEN gs % 5 = 1 THEN '24南京国资债00' || gs::text
    WHEN gs % 5 = 2 THEN '23苏州高新MTN00' || gs::text
    WHEN gs % 5 = 3 THEN '24无锡城发PPN00' || gs::text
    ELSE '25常州交通债00' || gs::text
  END,
  5000000.00 + gs * 23100.00
FROM generate_series(1, 60) AS gs;
INSERT INTO dm.fa_security_balance_zgxg_dm
SELECT
  '2026ZQDM060301',
  DATE '2026-06-03',
  'ZQ260603' || lpad(gs::text, 3, '0'),
  CASE
    WHEN gs % 5 = 0 THEN '25苏交控MTN00' || gs::text
    WHEN gs % 5 = 1 THEN '24南京国资债00' || gs::text
    WHEN gs % 5 = 2 THEN '23苏州高新MTN00' || gs::text
    WHEN gs % 5 = 3 THEN '24无锡城发PPN00' || gs::text
    ELSE '25常州交通债00' || gs::text
  END,
  CASE gs
    WHEN 5 THEN 5000000.00 + gs * 23100.00 - 80000.00
    WHEN 18 THEN 5000000.00 + gs * 23100.00 - 70000.00
    WHEN 41 THEN 5000000.00 + gs * 23100.00 + 25000.00
    ELSE 5000000.00 + gs * 23100.00
  END,
  0.00,
  0.00,
  '01',
  NULL,
  NULL
FROM generate_series(1, 60) AS gs;

-- B. 资产差异：债券 DM 只能部分解释，主原因显示“暂不明确具体资产差异，但多个债券...”
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-03', '2026ZQDM060302', '江苏信托-嘉泽稳收债券投资集合资金信托计划', 449700000.00, 450000000.00, 126000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026ZQDM060302', DATE '2026-06-03', '4001', '实收信托', 126000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026ZQDM060302', 'JS060302', DATE '2026-06-03', '0004', '资产合计', 450000000.00),
('2026ZQDM060302', 'JS060302', DATE '2026-06-03', '1002.01.01.01.430101551910060302', '招商银行南京分行托管户活期存款', 190818000.00);
INSERT INTO dws.fa_valuationreport_dws
SELECT
  '2026ZQDM060302',
  'JS060302',
  DATE '2026-06-03',
  '1501.01.08.01.ZQ260613' || lpad(gs::text, 3, '0'),
  CASE
    WHEN gs % 4 = 0 THEN '24苏科产债00' || gs::text
    WHEN gs % 4 = 1 THEN '23锡产业MTN00' || gs::text
    WHEN gs % 4 = 2 THEN '25宁河西PPN00' || gs::text
    ELSE '24扬州经开债00' || gs::text
  END,
  4200000.00 + gs * 18300.00
FROM generate_series(1, 55) AS gs;
INSERT INTO dm.fa_security_balance_zgxg_dm
SELECT
  '2026ZQDM060302',
  DATE '2026-06-03',
  'ZQ260613' || lpad(gs::text, 3, '0'),
  CASE
    WHEN gs % 4 = 0 THEN '24苏科产债00' || gs::text
    WHEN gs % 4 = 1 THEN '23锡产业MTN00' || gs::text
    WHEN gs % 4 = 2 THEN '25宁河西PPN00' || gs::text
    ELSE '24扬州经开债00' || gs::text
  END,
  CASE gs
    WHEN 8 THEN 4200000.00 + gs * 18300.00 - 100000.00
    WHEN 22 THEN 4200000.00 + gs * 18300.00 - 80000.00
    ELSE 4200000.00 + gs * 18300.00
  END,
  0.00,
  0.00,
  '01',
  NULL,
  NULL
FROM generate_series(1, 55) AS gs;

-- C. 资产缺失：全末级候选超过 50 行，前四段自然分组后贷款合同分组组合命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-03', '2026ZCZH060303', '江苏信托-新城更新贷款债权集合资金信托计划', 298550000.00, 300000000.00, 90000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026ZCZH060303', DATE '2026-06-03', '4001', '实收信托', 90000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026ZCZH060303', 'JS060303', DATE '2026-06-03', '0004', '资产合计', 300000000.00),
('2026ZCZH060303', 'JS060303', DATE '2026-06-03', '1002.01.01.01.430101551910060303', '中国银行江苏省分行托管户活期存款', 192548000.00);
INSERT INTO dws.fa_valuationreport_dws
SELECT
  '2026ZCZH060303',
  'JS060303',
  DATE '2026-06-03',
  '1101.02.05.01.ZQ260623' || lpad(gs::text, 3, '0'),
  '24江苏省地方政府债' || lpad(gs::text, 3, '0'),
  1800000.00 + gs * 9000.00
FROM generate_series(1, 52) AS gs;
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026ZCZH060303', 'JS060303', DATE '2026-06-03', '1303.01.01.01.DK20260603001', '南京雨花科创园流动资金贷款', 700000.00),
('2026ZCZH060303', 'JS060303', DATE '2026-06-03', '1303.01.01.01.DK20260603002', '苏州吴中产业园流动资金贷款', 750000.00);
INSERT INTO dm.am_projinvest_zgxg_dm VALUES
('2026ZCZH060303', DATE '2026-06-03', 'DK20260603001', 700000.00, NULL),
('2026ZCZH060303', DATE '2026-06-03', 'DK20260603002', 750000.00, NULL);

-- D. 负债权益：全末级候选超过 50 行，前四段费用分组组合命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-03', '2026FZQY060304', '江苏信托-江北产业园收益权集合资金信托计划', 380000000.00, 379650000.00, 120000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026FZQY060304', DATE '2026-06-03', '4001', '实收信托', 120000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026FZQY060304', 'JS060304', DATE '2026-06-03', '0004', '资产合计', 380000000.00);
INSERT INTO dws.fa_valuationreport_dws
SELECT
  '2026FZQY060304',
  'JS060304',
  DATE '2026-06-03',
  '2203.02.01.01.FEE' || lpad(gs::text, 3, '0'),
  '应付托管运营费用-' || lpad(gs::text, 3, '0'),
  6000.00 + gs * 100.00
FROM generate_series(1, 52) AS gs;
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026FZQY060304', 'JS060304', DATE '2026-06-03', '2203.02.99.01.FEE5301', '应付管理人报酬-南京信托运营部', 185000.00),
('2026FZQY060304', 'JS060304', DATE '2026-06-03', '2203.02.99.01.FEE5302', '应付托管费-交通银行江苏省分行', 165000.00);

-- E. 资产差异：逆回购与存续回购业务表金额差异完整解释。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-03', '2026NHHG060305', '江苏信托-宁沪短融逆回购管理集合资金信托计划', 320066800.00, 320000000.00, 100000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026NHHG060305', DATE '2026-06-03', '4001', '实收信托', 100000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026NHHG060305', 'JS060305', DATE '2026-06-03', '0004', '资产合计', 320000000.00),
('2026NHHG060305', 'JS060305', DATE '2026-06-03', '1002.01.01.01.430101551910060305', '工商银行南京汉中门支行活期存款', 281750000.00),
('2026NHHG060305', 'JS060305', DATE '2026-06-03', '1111.12.01.01.RGC26060301', '银行间质押式逆回购-隔夜', 15000000.00),
('2026NHHG060305', 'JS060305', DATE '2026-06-03', '1111.12.07.01.RGC26060302', '银行间质押式逆回购-7天', 12750000.00),
('2026NHHG060305', 'JS060305', DATE '2026-06-03', '1111.12.14.01.RGC26060303', '交易所质押式逆回购-14天', 10500000.00);
INSERT INTO assman_reg.ex_pledge_back VALUES
('2026NHHG060305', '700101', 15200000.00, 25000.00),
('2026NHHG060305', '700102', 12750000.00, 41800.00),
('2026NHHG060305', '700103', 10250000.00, 50000.00);

-- F. 组合场景：资产端债券 DM 完整解释后，继续进入正回购存续回购业务表金额核对。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-06-03', '2026ZHCE060306', '江苏信托-江南稳健债券回购组合集合资金信托计划', 519900000.00, 519950000.00, 160000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2026ZHCE060306', DATE '2026-06-03', '4001', '实收信托', 160000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2026ZHCE060306', 'JS060306', DATE '2026-06-03', '0004', '资产合计', 520000000.00),
('2026ZHCE060306', 'JS060306', DATE '2026-06-03', '1002.01.01.01.430101551910060306', '建设银行江苏省分行托管户活期存款', 236208000.00),
('2026ZHCE060306', 'JS060306', DATE '2026-06-03', '2111.06.03.01.RP260603', '卖出回购金融资产款-银行间质押式正回购', 2500000.00);
INSERT INTO dws.fa_valuationreport_dws
SELECT
  '2026ZHCE060306',
  'JS060306',
  DATE '2026-06-03',
  '1101.02.09.01.ZH260603' || lpad(gs::text, 3, '0'),
  CASE
    WHEN gs % 3 = 0 THEN '24江宁国资MTN00' || gs::text
    WHEN gs % 3 = 1 THEN '25苏高新债00' || gs::text
    ELSE '23南京地铁MTN00' || gs::text
  END,
  4700000.00 + gs * 14800.00
FROM generate_series(1, 55) AS gs;
INSERT INTO dm.fa_security_balance_zgxg_dm
SELECT
  '2026ZHCE060306',
  DATE '2026-06-03',
  'ZH260603' || lpad(gs::text, 3, '0'),
  CASE
    WHEN gs % 3 = 0 THEN '24江宁国资MTN00' || gs::text
    WHEN gs % 3 = 1 THEN '25苏高新债00' || gs::text
    ELSE '23南京地铁MTN00' || gs::text
  END,
  CASE gs
    WHEN 6 THEN 4700000.00 + gs * 14800.00 - 60000.00
    WHEN 44 THEN 4700000.00 + gs * 14800.00 - 40000.00
    ELSE 4700000.00 + gs * 14800.00
  END,
  0.00,
  0.00,
  '01',
  NULL,
  NULL
FROM generate_series(1, 55) AS gs;
INSERT INTO assman_reg.ex_pledge_back VALUES
('2026ZHCE060306', '800603', 2480000.00, 30000.00);

INSERT INTO dws.currency_report_duration
SELECT 'CRD-20260603-' || projinnercode, caldate, projinnercode, projname, c1000
FROM dws.zf_detail_2024
WHERE caldate = DATE '2026-06-03'
  AND projinnercode LIKE '2026%0603%';

COMMIT;
