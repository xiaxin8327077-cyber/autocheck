-- 2026-05-20 小批量场景数据。
-- 目的：覆盖当前已实现的全部预估差异原因，便于页面和导出功能回归测试。
-- 如本地库还停留在旧测试结构，本脚本会补齐本批数据依赖的测试表字段。

CREATE SCHEMA IF NOT EXISTS dws;

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

ALTER TABLE dws.fa_valuationreport_dws
  ADD COLUMN IF NOT EXISTS c_projcode varchar;

CREATE TABLE IF NOT EXISTS dws.am_pactasset_dws (
  c_projcode varchar,
  d_cldate date,
  c_pactid varchar,
  c_udlyasset varchar,
  c_stockcode varchar
);

ALTER TABLE dws.am_pactasset_dws
  ADD COLUMN IF NOT EXISTS c_pactid varchar;

CREATE TABLE IF NOT EXISTS dws.am_projinvest_dws (
  c_projcode varchar,
  d_cldate date,
  c_pactid varchar,
  f_acbalance numeric
);

BEGIN;

DELETE FROM dws.am_projinvest_dws
 WHERE d_cldate = DATE '2026-05-20'
   AND c_projcode LIKE 'T20260520_%';

DELETE FROM dws.am_pactasset_dws
 WHERE d_cldate = DATE '2026-05-20'
   AND c_projcode LIKE 'T20260520_%';

DELETE FROM dws.fa_valuationreport_dws
 WHERE d_valuationdate = DATE '2026-05-20'
   AND c_projcode LIKE 'T20260520_%';

DELETE FROM dws.fa_accountbalance_dws
 WHERE d_balancedate = DATE '2026-05-20'
   AND c_projcode LIKE 'T20260520_%';

DELETE FROM dws.currency_report_duration
 WHERE caldate = DATE '2026-05-20'
   AND c_projectcode LIKE 'T20260520_%';

DELETE FROM dws.zf_detail_2024
 WHERE caldate = DATE '2026-05-20'
   AND projinnercode LIKE 'T20260520_%';

-- 1. 资产缺失：资产合计小于估值表资产合计，命中非 1101.05.03.01 的 1 开头末级科目。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_ASSET_MISS', '华鑫信托-资产缺失小额回归样例', 900000.00, 1000000.00, 500000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_ASSET_MISS', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-ASSET-MISS-01', DATE '2026-05-20', 'T20260520_ASSET_MISS', '华鑫信托-资产缺失小额回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_ASSET_MISS', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_ASSET_MISS', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000001', '银行存款-测试专户', 900000.00),
('T20260520_ASSET_MISS', 'JS0520', DATE '2026-05-20', '1101.02.15.01.0001', '25华鑫债权资产A', 100000.00);

-- 2. 资产重复：资产合计大于估值表资产合计，命中 1 开头末级科目。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_ASSET_DUP', '华鑫信托-资产重复小额回归样例', 1100000.00, 1000000.00, 500000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_ASSET_DUP', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-ASSET-DUP-01', DATE '2026-05-20', 'T20260520_ASSET_DUP', '华鑫信托-资产重复小额回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_ASSET_DUP', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_ASSET_DUP', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000002', '银行存款-募集户', 900000.00),
('T20260520_ASSET_DUP', 'JS0520', DATE '2026-05-20', '1101.02.15.01.0002', '25华鑫债权资产B', 100000.00);

-- 3. AM 标的缺失：资产缺失且四级科目为 1101.05.03.01，但 AM 资产信息表找不到相同或高匹配资产名称。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_AM_MISSING', '华鑫信托-AM标的缺失回归样例', 900000.00, 1000000.00, 500000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_AM_MISSING', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-AM-MISSING-01', DATE '2026-05-20', 'T20260520_AM_MISSING', '华鑫信托-AM标的缺失回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_AM_MISSING', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_AM_MISSING', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000003', '银行存款-监管户', 900000.00),
('T20260520_AM_MISSING', 'JS0520', DATE '2026-05-20', '1101.05.03.01.0003', '恒润供应链应收款资产C', 100000.00);
INSERT INTO dws.am_pactasset_dws (c_projcode, d_cldate, c_pactid, c_udlyasset, c_stockcode) VALUES
('T20260520_AM_MISSING', DATE '2026-05-20', 'PACT-0520-MISSING-OTHER', '完全不同的存量资产', '990003');

-- 4. FA 与 AM 标的不一致：资产名称匹配，但 FA 科目末段代码与 AM 标的代码不一致。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_AM_MISMATCH', '华鑫信托-FA与AM标的不一致回归样例', 900000.00, 1000000.00, 500000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_AM_MISMATCH', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-AM-MISMATCH-01', DATE '2026-05-20', 'T20260520_AM_MISMATCH', '华鑫信托-FA与AM标的不一致回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_AM_MISMATCH', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_AM_MISMATCH', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000004', '银行存款-监管户', 900000.00),
('T20260520_AM_MISMATCH', 'JS0520', DATE '2026-05-20', '1101.05.03.01.0004', '稳益信托贷款资产D', 100000.00);
INSERT INTO dws.am_pactasset_dws (c_projcode, d_cldate, c_pactid, c_udlyasset, c_stockcode) VALUES
('T20260520_AM_MISMATCH', DATE '2026-05-20', 'PACT-0520-MISMATCH', '稳益信托贷款资产D', '900004');
INSERT INTO dws.am_projinvest_dws (c_projcode, d_cldate, c_pactid, f_acbalance) VALUES
('T20260520_AM_MISMATCH', DATE '2026-05-20', 'PACT-0520-MISMATCH', 100000.00);

-- 5. 合同投融资余额为 0：资产名称和标的代码均匹配，但合同投融资余额为 0。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_INVEST_ZERO', '华鑫信托-合同投融资余额为零回归样例', 900000.00, 1000000.00, 500000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_INVEST_ZERO', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-INVEST-ZERO-01', DATE '2026-05-20', 'T20260520_INVEST_ZERO', '华鑫信托-合同投融资余额为零回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_INVEST_ZERO', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_INVEST_ZERO', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000005', '银行存款-监管户', 900000.00),
('T20260520_INVEST_ZERO', 'JS0520', DATE '2026-05-20', '1101.05.03.01.0005', '鼎盛项目贷款资产E', 100000.00);
INSERT INTO dws.am_pactasset_dws (c_projcode, d_cldate, c_pactid, c_udlyasset, c_stockcode) VALUES
('T20260520_INVEST_ZERO', DATE '2026-05-20', 'PACT-0520-ZERO', '鼎盛项目贷款资产E', '0005');
INSERT INTO dws.am_projinvest_dws (c_projcode, d_cldate, c_pactid, f_acbalance) VALUES
('T20260520_INVEST_ZERO', DATE '2026-05-20', 'PACT-0520-ZERO', 0.00);

-- 6. 缺失资产在 AM 信息中正常：使用高匹配度名称命中 AM 资产，标的代码一致，合同投融资余额不为 0。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_INVEST_OK', '华鑫信托-AM信息正常需排SQL回归样例', 900000.00, 1000000.00, 500000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_INVEST_OK', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-INVEST-OK-01', DATE '2026-05-20', 'T20260520_INVEST_OK', '华鑫信托-AM信息正常需排SQL回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_INVEST_OK', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_INVEST_OK', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000006', '银行存款-监管户', 900000.00),
('T20260520_INVEST_OK', 'JS0520', DATE '2026-05-20', '1101.05.03.01.0006', '星河项目贷款资产F_估值调整', 100000.00);
INSERT INTO dws.am_pactasset_dws (c_projcode, d_cldate, c_pactid, c_udlyasset, c_stockcode) VALUES
('T20260520_INVEST_OK', DATE '2026-05-20', 'PACT-0520-OK', '星河项目贷款资产F', '0006');
INSERT INTO dws.am_projinvest_dws (c_projcode, d_cldate, c_pactid, f_acbalance) VALUES
('T20260520_INVEST_OK', DATE '2026-05-20', 'PACT-0520-OK', 100000.00);

-- 7. 实收信托有误：a0001 与估值表 0004 一致，c1000 与 FA 4001 的差额等于主差异。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_RECEIVED', '华鑫信托-实收信托有误回归样例', 1000000.00, 900000.00, 400000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_RECEIVED', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-RECEIVED-01', DATE '2026-05-20', 'T20260520_RECEIVED', '华鑫信托-实收信托有误回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_RECEIVED', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_RECEIVED', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000007', '银行存款-托管户', 1000000.00);

-- 8. 负债及权益科目差异：资产合计正确，c1000 正确，非 1 开头估值科目能命中主差异。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_LIAB', '华鑫信托-负债权益科目差异回归样例', 1000000.00, 950000.00, 500000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_LIAB', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-LIAB-01', DATE '2026-05-20', 'T20260520_LIAB', '华鑫信托-负债权益科目差异回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_LIAB', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_LIAB', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000008', '银行存款-托管户', 1000000.00),
('T20260520_LIAB', 'JS0520', DATE '2026-05-20', '2203', '应付管理人报酬', 50000.00);

-- 9. 暂无法确定：资产合计正确，c1000 正确，估值表非 1 开头科目不能命中主差异。
INSERT INTO dws.zf_detail_2024 (caldate, projinnercode, projname, a0001, d0000, c1000) VALUES
(DATE '2026-05-20', 'T20260520_UNKNOWN', '华鑫信托-暂无法确定回归样例', 1000000.00, 950000.00, 500000.00);
INSERT INTO dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode, c_accountname, f_balance) VALUES
('T20260520_UNKNOWN', DATE '2026-05-20', '4001', '实收信托', 500000.00);
INSERT INTO dws.currency_report_duration (id1, caldate, c_projectcode, c_projectname, f_assetshare) VALUES
('CRD-20260520-UNKNOWN-01', DATE '2026-05-20', 'T20260520_UNKNOWN', '华鑫信托-暂无法确定回归样例', 500000.00);
INSERT INTO dws.fa_valuationreport_dws (c_projcode, c_assetcode, d_valuationdate, c_accountcode, c_accountname, f_marketvalue) VALUES
('T20260520_UNKNOWN', 'JS0520', DATE '2026-05-20', '0004', '资产合计', 1000000.00),
('T20260520_UNKNOWN', 'JS0520', DATE '2026-05-20', '1002.01.01.01.622202010000009', '银行存款-托管户', 1000000.00),
('T20260520_UNKNOWN', 'JS0520', DATE '2026-05-20', '2203', '应付管理人报酬', 30000.00);

ANALYZE dws.zf_detail_2024;
ANALYZE dws.fa_accountbalance_dws;
ANALYZE dws.currency_report_duration;
ANALYZE dws.fa_valuationreport_dws;
ANALYZE dws.am_pactasset_dws;
ANALYZE dws.am_projinvest_dws;

COMMIT;
