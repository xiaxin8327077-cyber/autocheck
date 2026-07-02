-- 2026-05-31 自动对数真实化回归场景数据。
-- 目的：重建本地 auto_check_test 库中的对数核心表，清理旧测试数据，并生成更贴近业务命名的核对结果。
-- 使用方式：powershell -ExecutionPolicy Bypass -File scripts\load-local-pg-20260531-ta-scenarios.ps1

CREATE SCHEMA IF NOT EXISTS dws;
CREATE SCHEMA IF NOT EXISTS dm;
CREATE SCHEMA IF NOT EXISTS zgxg_zhbs;
CREATE SCHEMA IF NOT EXISTS currency_report_24;
CREATE SCHEMA IF NOT EXISTS ass_man_reg;

BEGIN;

DROP TABLE IF EXISTS dws.zf_detail_2024;
DROP TABLE IF EXISTS dws.currency_report_duration;
DROP TABLE IF EXISTS dws.fa_accountbalance_dws;
DROP TABLE IF EXISTS dws.fa_valuationreport_dws;
DROP TABLE IF EXISTS dws.am_pactasset_dws;
DROP TABLE IF EXISTS dws.am_projinvest_dws;
DROP TABLE IF EXISTS dws.ta_pact_detail_dws;
DROP TABLE IF EXISTS dm.ta_pact_survamt_day_zgxg_dm CASCADE;
DROP TABLE IF EXISTS dm.fa_security_balance_zgxg_dm;
DROP TABLE IF EXISTS dm.am_projinvest_zgxg_dm;
DROP TABLE IF EXISTS dm.am_projinvest_spv_zgxg_dm;
DROP TABLE IF EXISTS zgxg_zhbs.ccqxx;
DROP TABLE IF EXISTS currency_report_24.currency_detail_project_2_1_2;
DROP TABLE IF EXISTS currency_report_24.currency_detail_project_2_1_4;
DROP TABLE IF EXISTS currency_report_24.currency_detail_project_2_1_5;
DROP TABLE IF EXISTS currency_report_24.currency_detail_project_2_1_5_2;
DROP TABLE IF EXISTS currency_report_24.currency_detail_project_2_1_6;
DROP TABLE IF EXISTS currency_report_24.currency_detail_project_2_1_9;
DROP TABLE IF EXISTS ass_man_reg.ex_pledge_back;

CREATE TABLE dws.zf_detail_2024 (
  caldate date NOT NULL,
  projinnercode varchar NOT NULL,
  projname varchar NOT NULL,
  a0001 numeric NOT NULL,
  d0000 numeric NOT NULL,
  c1000 numeric NOT NULL
);

CREATE TABLE dws.currency_report_duration (
  id1 varchar PRIMARY KEY,
  caldate date,
  c_projectcode varchar,
  c_projectname varchar,
  f_assetshare numeric
);

CREATE TABLE dws.fa_accountbalance_dws (
  c_projcode varchar,
  d_balancedate date,
  c_accountcode varchar,
  c_accountname varchar,
  f_balance numeric
);

CREATE TABLE dws.fa_valuationreport_dws (
  c_projcode varchar,
  c_assetcode varchar,
  d_valuationdate date,
  c_accountcode varchar,
  c_accountname varchar,
  f_marketvalue numeric
);

CREATE TABLE dws.am_pactasset_dws (
  c_projcode varchar,
  d_cldate date,
  c_pactid varchar,
  c_udlyasset varchar,
  c_stockcode varchar
);

CREATE TABLE dws.am_projinvest_dws (
  c_projcode varchar,
  d_cldate date,
  c_pactid varchar,
  f_acbalance numeric
);

CREATE TABLE dws.ta_pact_detail_dws (
  d_cldate date,
  c_projcode varchar,
  c_pactid varchar,
  f_shareamt numeric,
  f_alltincom numeric
);

CREATE TABLE dm.ta_pact_survamt_day_zgxg_dm (
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

CREATE TABLE dm.fa_security_balance_zgxg_dm (
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

CREATE TABLE dm.am_projinvest_zgxg_dm (
  pin_projcode varchar,
  pin_cldate date,
  pin_mpactid varchar,
  pin_acbalance numeric,
  pin_gqtype_h varchar
);

CREATE TABLE dm.am_projinvest_spv_zgxg_dm (
  svd_projcode varchar,
  svd_cldate date,
  svd_mpactid varchar,
  svd_balamoney_cost numeric,
  svd_balamoney_inte numeric,
  svd_balamoney_fair numeric,
  svd_assettype varchar
);

CREATE TABLE zgxg_zhbs.ccqxx (
  pjdw_projcode varchar,
  pin_mpactid varchar,
  pin_acbalance numeric
);

CREATE TABLE currency_report_24.currency_detail_project_2_1_2 (caldate date);
CREATE TABLE currency_report_24.currency_detail_project_2_1_4 (caldate date);
CREATE TABLE currency_report_24.currency_detail_project_2_1_5 (caldate date);
CREATE TABLE currency_report_24.currency_detail_project_2_1_5_2 (caldate date);
CREATE TABLE currency_report_24.currency_detail_project_2_1_6 (caldate date);
CREATE TABLE currency_report_24.currency_detail_project_2_1_9 (caldate date);

CREATE TABLE ass_man_reg.ex_pledge_back (
  project_code varchar,
  subcode varchar,
  buyback_money numeric,
  expenses numeric
);

-- 1. 资产缺失：资产少记，具体缺失资产命中，同时 AM 标的缺失作为详情展示。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2024JDC0485', '江苏信托-丰润致远财富传承信托12号', 99800000.00, 100000000.00, 32000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2024JDC0485', DATE '2026-05-31', '4001', '实收信托', 32000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2024JDC0485-01', DATE '2026-05-31', '2024JDC0485', '江苏信托-丰润致远财富传承信托12号', 32000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2024JDC0485', 'AM-2024JDC0485', DATE '2026-05-31', '0004', '资产合计', 100000000.00),
('2024JDC0485', 'AM-2024JDC0485', DATE '2026-05-31', '1101.05.03.01.FRZY12', '丰润致远12号债权还款协议书', 200000.00),
('2024JDC0485', 'AM-2024JDC0485', DATE '2026-05-31', '1002.01.01.01.10298200010001', '中国工商银行南京江宁支行', 12560000.00);

-- 2. 资产缺失：资产少记，具体缺失资产命中，AM 资产名称匹配但标的代码不一致。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025JXTL9009', '江苏信托-金信添利9号集合资金信托计划', 88620000.00, 88800000.00, 26000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025JXTL9009', DATE '2026-05-31', '4001', '实收信托', 26000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025JXTL9009-01', DATE '2026-05-31', '2025JXTL9009', '江苏信托-金信添利9号集合资金信托计划', 26000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025JXTL9009', 'AM-2025JXTL9009', DATE '2026-05-31', '0004', '资产合计', 88800000.00),
('2025JXTL9009', 'AM-2025JXTL9009', DATE '2026-05-31', '1101.05.03.01.JXTL09', '金信添利9号集合资金信托计划收益权', 90000.00),
('2025JXTL9009', 'AM-2025JXTL9009', DATE '2026-05-31', '1101.04.01.01.000001', '华夏成长基金', 90000.00),
('2025JXTL9009', 'AM-2025JXTL9009', DATE '2026-05-31', '1002.01.01.01.10298200010002', '中国工商银行南京城东支行', 8720000.00);
INSERT INTO dws.am_pactasset_dws VALUES
('2025JXTL9009', DATE '2026-05-31', 'JSXT-AM-202505310091', '金信添利9号集合资金信托计划收益权', 'JXTL08');

-- 3. 资产重复：资产多记，1 开头资产明细能命中多出的金额。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2023ZQJH1188', '江苏信托-中债优选债券投资集合资金信托计划', 120150000.00, 120000000.00, 50000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2023ZQJH1188', DATE '2026-05-31', '4001', '实收信托', 50000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2023ZQJH1188-01', DATE '2026-05-31', '2023ZQJH1188', '江苏信托-中债优选债券投资集合资金信托计划', 50000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2023ZQJH1188', 'AM-2023ZQJH1188', DATE '2026-05-31', '0004', '资产合计', 120000000.00),
('2023ZQJH1188', 'AM-2023ZQJH1188', DATE '2026-05-31', '1501.01.02.01.102381204', '23苏城投MTN004', 60000.00),
('2023ZQJH1188', 'AM-2023ZQJH1188', DATE '2026-05-31', '1101.01.01.01.600000', '浦发银行', 40000.00),
('2023ZQJH1188', 'AM-2023ZQJH1188', DATE '2026-05-31', '1111.12.34.01.RGC001', '质押式逆回购', 30000.00),
('2023ZQJH1188', 'AM-2023ZQJH1188', DATE '2026-05-31', '1501.04.05.01.DK20260531001', '流动资金贷款', 20000.00),
('2023ZQJH1188', 'AM-2023ZQJH1188', DATE '2026-05-31', '1002.01.01.01.4301015519100680766', '交通银行南京城中支行', 3850000.00);

-- 4. 资产差异：1541 财产权合同投融资余额与 FA 估值金额差异命中主差异。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2024FRZY0012', '江苏信托-丰润致远财富传承信托12号财产权单元', 150000000.00, 150300000.00, 80000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2024FRZY0012', DATE '2026-05-31', '4001', '实收信托', 80000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2024FRZY0012-01', DATE '2026-05-31', '2024FRZY0012', '江苏信托-丰润致远财富传承信托12号财产权单元', 80000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2024FRZY0012', 'AM-2024FRZY0012', DATE '2026-05-31', '0004', '资产合计', 150300000.00),
('2024FRZY0012', 'AM-2024FRZY0012', DATE '2026-05-31', '1541.01.FRZY12A', '丰润致远12号债权还款协议书1', 50000000.00),
('2024FRZY0012', 'AM-2024FRZY0012', DATE '2026-05-31', '1541.01.FRZY12B', '丰润致远12号债权还款协议书2', 30000000.00);
INSERT INTO dws.am_projinvest_dws VALUES
('2024FRZY0012', DATE '2026-05-31', 'FRZY12A', 49800000.00),
('2024FRZY0012', DATE '2026-05-31', 'FRZY12B', 29900000.00);

-- 5. 负债及权益科目缺失：资产正确、实收本金正确，d0000 少记，非 1 开头科目命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025JHZX0666', '江苏信托-嘉和甄选债券投资集合资金信托计划', 180000000.00, 179920000.00, 76000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025JHZX0666', DATE '2026-05-31', '4001', '实收信托', 76000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025JHZX0666-01', DATE '2026-05-31', '2025JHZX0666', '江苏信托-嘉和甄选债券投资集合资金信托计划', 76000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025JHZX0666', 'AM-2025JHZX0666', DATE '2026-05-31', '0004', '资产合计', 180000000.00),
('2025JHZX0666', 'AM-2025JHZX0666', DATE '2026-05-31', '2001.01', '应付管理人报酬', 80000.00);

-- 6. 负债及权益科目重复：资产正确、实收本金正确，d0000 多记，非 1 开头科目按绝对值命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025HYLC0088', '江苏信托-恒盈现金管理服务信托', 96000000.00, 96060000.00, 40000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025HYLC0088', DATE '2026-05-31', '4001', '实收信托', 40000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025HYLC0088-01', DATE '2026-05-31', '2025HYLC0088', '江苏信托-恒盈现金管理服务信托', 40000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025HYLC0088', 'AM-2025HYLC0088', DATE '2026-05-31', '0004', '资产合计', 96000000.00),
('2025HYLC0088', 'AM-2025HYLC0088', DATE '2026-05-31', '2111.12.34.01.RP001', '卖出回购金融资产款', 60000.00);

-- 7. 负债及权益科目差异：资产正确、实收本金正确，但非 1 开头科目无法直接命中。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025WJFW0999', '江苏信托-稳健财富传承服务信托', 236801234.56, 236726234.56, 100000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025WJFW0999', DATE '2026-05-31', '4001', '实收信托', 100000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025WJFW0999-01', DATE '2026-05-31', '2025WJFW0999', '江苏信托-稳健财富传承服务信托', 100000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025WJFW0999', 'AM-2025WJFW0999', DATE '2026-05-31', '0004', '资产合计', 236801234.56),
('2025WJFW0999', 'AM-2025WJFW0999', DATE '2026-05-31', '2001.01', '应付管理人报酬', 20000.00),
('2025WJFW0999', 'AM-2025WJFW0999', DATE '2026-05-31', '2203.01', '应付托管费', 30000.00);

-- 8. 实收本金缺失：主差异等于整笔 FA 4001。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025RJYL0007', '江苏信托-瑞景养老保障集合资金信托计划', 110000000.00, 70000000.00, 0.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025RJYL0007', DATE '2026-05-31', '4001', '实收信托', 40000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025RJYL0007-01', DATE '2026-05-31', '2025RJYL0007', '江苏信托-瑞景养老保障集合资金信托计划', 0.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025RJYL0007', 'AM-2025RJYL0007', DATE '2026-05-31', '0004', '资产合计', 110000000.00);

-- 9. 实收本金重复：主差异等于负的整笔 FA 4001。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025QYJH0008', '江苏信托-启元家族信托8号', 90000000.00, 126000000.00, 72000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025QYJH0008', DATE '2026-05-31', '4001', '实收信托', 36000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025QYJH0008-01', DATE '2026-05-31', '2025QYJH0008', '江苏信托-启元家族信托8号', 72000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025QYJH0008', 'AM-2025QYJH0008', DATE '2026-05-31', '0004', '资产合计', 90000000.00);

-- 10. 实收本金差异：TA 汇总不一致，但 DM-DWS 差额不等于 4001-c1000，仅作为详情核对信息展示。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025XTJH1001', '江苏信托-鑫泰聚合1号集合资金信托计划', 210000000.00, 209850000.00, 59850000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025XTJH1001', DATE '2026-05-31', '4001', '实收信托', 60000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025XTJH1001-01', DATE '2026-05-31', '2025XTJH1001', '江苏信托-鑫泰聚合1号集合资金信托计划', 59850000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025XTJH1001', 'AM-2025XTJH1001', DATE '2026-05-31', '0004', '资产合计', 210000000.00);
INSERT INTO dm.ta_pact_survamt_day_zgxg_dm VALUES
(DATE '2026-05-31', '2025XTJH1001', 'JSXT202505310001', '南京长江产业投资集团有限公司', '3', '30', 'SPV01', 135000.00, 59685000.00);
INSERT INTO dws.ta_pact_detail_dws VALUES
(DATE '2026-05-31', '2025XTJH1001', 'JSXT202505310001', 59850000.00, 150000.00);

-- 11. 实收本金差异：客户类型依赖字段为空，空值金额合计命中 4001-c1000。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025RHWH2002', '江苏信托-润和稳汇2号集合资金信托计划', 175000000.00, 174880000.00, 44880000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025RHWH2002', DATE '2026-05-31', '4001', '实收信托', 45000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025RHWH2002-01', DATE '2026-05-31', '2025RHWH2002', '江苏信托-润和稳汇2号集合资金信托计划', 44880000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025RHWH2002', 'AM-2025RHWH2002', DATE '2026-05-31', '0004', '资产合计', 175000000.00);
INSERT INTO dm.ta_pact_survamt_day_zgxg_dm VALUES
(DATE '2026-05-31', '2025RHWH2002', 'JSXT202505310021', '苏州工业园区国有资本投资有限公司', '4', NULL, 'SPV02', 20000.00, 100000.00),
(DATE '2026-05-31', '2025RHWH2002', 'JSXT202505310022', '江苏省国际信托有限责任公司', '1', '10', 'SPV01', 80000.00, 44800000.00);
INSERT INTO dws.ta_pact_detail_dws VALUES
(DATE '2026-05-31', '2025RHWH2002', 'JSXT202505310021', 100000.00, 20000.00),
(DATE '2026-05-31', '2025RHWH2002', 'JSXT202505310022', 44800000.00, 80000.00);

-- 12. 实收本金差异：TA 细分无法进一步解释，具体原因保留为实收信托有误。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025JXTL3003', '江苏信托-金信添利3号集合资金信托计划', 98000000.00, 97910000.00, 29910000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025JXTL3003', DATE '2026-05-31', '4001', '实收信托', 30000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025JXTL3003-01', DATE '2026-05-31', '2025JXTL3003', '江苏信托-金信添利3号集合资金信托计划', 29910000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025JXTL3003', 'AM-2025JXTL3003', DATE '2026-05-31', '0004', '资产合计', 98000000.00);
INSERT INTO dm.ta_pact_survamt_day_zgxg_dm VALUES
(DATE '2026-05-31', '2025JXTL3003', 'JSXT202505310031', '上海浦东发展银行股份有限公司南京分行', '5', '50', NULL, 10000.00, 20000.00),
(DATE '2026-05-31', '2025JXTL3003', 'JSXT202505310032', '江苏高科技投资集团有限公司', '1', '10', 'SPV01', 90000.00, 29880000.00);
INSERT INTO dws.ta_pact_detail_dws VALUES
(DATE '2026-05-31', '2025JXTL3003', 'JSXT202505310031', 20000.00, 10000.00),
(DATE '2026-05-31', '2025JXTL3003', 'JSXT202505310032', 29880000.00, 90000.00);

-- 13. 3.4 混合场景：资产正确、c1000 与 FA 4001 不一致，实收差额不能单独解释主差异，剩余差额未命中非 1 科目。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025YHZX9009', '江苏信托-银辉甄选9号集合资金信托计划', 130000000.00, 129900000.00, 49800000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025YHZX9009', DATE '2026-05-31', '4001', '实收信托', 50000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025YHZX9009-01', DATE '2026-05-31', '2025YHZX9009', '江苏信托-银辉甄选9号集合资金信托计划', 49800000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025YHZX9009', 'AM-2025YHZX9009', DATE '2026-05-31', '0004', '资产合计', 130000000.00);

-- 14. 3.4 混合场景：剩余差额为正且命中非 1 科目，归为负债及权益科目缺失。
-- 主差异=150000，4001-c1000=70000，剩余差额=80000。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025RYZX4004', '江苏信托-瑞盈甄选4号集合资金信托计划', 160000000.00, 159850000.00, 59930000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025RYZX4004', DATE '2026-05-31', '4001', '实收信托', 60000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025RYZX4004-01', DATE '2026-05-31', '2025RYZX4004', '江苏信托-瑞盈甄选4号集合资金信托计划', 59930000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025RYZX4004', 'AM-2025RYZX4004', DATE '2026-05-31', '0004', '资产合计', 160000000.00),
('2025RYZX4004', 'AM-2025RYZX4004', DATE '2026-05-31', '2001.01', '应付管理人报酬', 80000.00);

-- 15. 3.4 混合场景：剩余差额为负且按绝对值命中非 1 科目，归为负债及权益科目重复。
-- 主差异=30000，4001-c1000=100000，剩余差额=-70000。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025ZCRH5005', '江苏信托-臻诚润汇5号集合资金信托计划', 140000000.00, 139970000.00, 39900000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025ZCRH5005', DATE '2026-05-31', '4001', '实收信托', 40000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025ZCRH5005-01', DATE '2026-05-31', '2025ZCRH5005', '江苏信托-臻诚润汇5号集合资金信托计划', 39900000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025ZCRH5005', 'AM-2025ZCRH5005', DATE '2026-05-31', '0004', '资产合计', 140000000.00),
('2025ZCRH5005', 'AM-2025ZCRH5005', DATE '2026-05-31', '2203.01', '应付托管费', 70000.00);

-- 16. 暂无法确定：主表存在差异，但估值表缺少 0004 资产合计，无法判断资产侧是否正确。
INSERT INTO dws.zf_detail_2024 VALUES
(DATE '2026-05-31', '2025ZWSJ0016', '江苏信托-卓稳数据缺失测试集合资金信托计划', 72000000.00, 71960000.00, 28000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2025ZWSJ0016', DATE '2026-05-31', '4001', '实收信托', 28000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202605-2025ZWSJ0016-01', DATE '2026-05-31', '2025ZWSJ0016', '江苏信托-卓稳数据缺失测试集合资金信托计划', 28000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2025ZWSJ0016', 'AM-2025ZWSJ0016', DATE '2026-05-31', '2001.01', '应付管理人报酬', 40000.00);

CREATE INDEX zf_detail_2024_date_idx ON dws.zf_detail_2024 (caldate);
CREATE INDEX currency_report_duration_project_date_idx ON dws.currency_report_duration (c_projectcode, caldate);
CREATE INDEX fa_accountbalance_project_date_acc_idx ON dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode);
CREATE INDEX fa_valuation_project_date_idx ON dws.fa_valuationreport_dws (c_projcode, d_valuationdate);
CREATE INDEX am_pactasset_project_date_asset_idx ON dws.am_pactasset_dws (c_projcode, d_cldate, c_udlyasset);
CREATE INDEX am_projinvest_project_date_pact_idx ON dws.am_projinvest_dws (c_projcode, d_cldate, c_pactid);
CREATE INDEX ta_pact_detail_project_date_idx ON dws.ta_pact_detail_dws (c_projcode, d_cldate);
CREATE INDEX ta_pact_survamt_project_date_idx ON dm.ta_pact_survamt_day_zgxg_dm (tpm_tcmpcode, tpm_date);

ANALYZE dws.zf_detail_2024;
ANALYZE dws.fa_accountbalance_dws;
ANALYZE dws.fa_valuationreport_dws;
ANALYZE dws.am_pactasset_dws;
ANALYZE dws.am_projinvest_dws;
ANALYZE dws.ta_pact_detail_dws;
ANALYZE dm.ta_pact_survamt_day_zgxg_dm;

COMMIT;
