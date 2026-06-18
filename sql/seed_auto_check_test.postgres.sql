CREATE SCHEMA IF NOT EXISTS dws;

DROP TABLE IF EXISTS dws.zf_detail_2024;
DROP TABLE IF EXISTS dws.currency_report_duration;
DROP TABLE IF EXISTS dws.fa_accountbalance_dws;
DROP TABLE IF EXISTS dws.fa_valuationreport_dws;
DROP TABLE IF EXISTS dws.am_pactasset_dws;
DROP TABLE IF EXISTS dws.am_projinvest_dws;

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

-- 1. 资产缺失：zf_detail a0001 小于估值表 0004 资产合计，1 开头末级科目能命中缺口；AM 标的代码也不一致。
INSERT INTO dws.zf_detail_2024 VALUES
('2026-04-30', '2020SJQ0529', '华鑫信托-聚鑫5号集合资金信托计划', 1171320069.10, 1172266385.70, 500000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2020SJQ0529', '2026-04-30', '4001', '实收信托', 500000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202604-2020SJQ0529-01', '2026-04-30', '2020SJQ0529', '华鑫信托-聚鑫5号集合资金信托计划', 500000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2020SJQ0529', 'JS0599', '2026-04-30', '0004', '资产合计', 1172266385.70),
('2020SJQ0529', 'JS0599', '2026-04-30', '1101.02.15.01.244733', 'G26资控1', 946316.60),
('2020SJQ0529', 'JS0599', '2026-04-30', '1101.02.15.01.244978', '26冀控K1', 21402.74),
('2020SJQ0529', 'JS0599', '2026-04-30', '1002.01.01.01.4301015519100680766', '工商银行南京江宁支行', 1056602849.82);
INSERT INTO dws.am_pactasset_dws VALUES
('2020SJQ0529', '2026-04-30', 'PACT-2020-001', 'G26资控1', '244978');
INSERT INTO dws.am_projinvest_dws VALUES
('2020SJQ0529', '2026-04-30', 'PACT-2020-001', 100000.00);

-- 2. 资产重复：zf_detail a0001 大于估值表 0004 资产合计，1 开头末级科目能命中多出的金额。
INSERT INTO dws.zf_detail_2024 VALUES
('2026-04-30', '2021ZQJH1188', '华鑫信托-中债优选债券投资集合资金信托计划', 908732456.44, 908615278.94, 300000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2021ZQJH1188', '2026-04-30', '4001', '实收信托', 300000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202604-2021ZQJH1188-01', '2026-04-30', '2021ZQJH1188', '华鑫信托-中债优选债券投资集合资金信托计划', 300000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2021ZQJH1188', 'JS0599', '2026-04-30', '0004', '资产合计', 908615278.94),
('2021ZQJH1188', 'JS0599', '2026-04-30', '1101.02.15.01.251175', '23苏华04', 117177.50),
('2021ZQJH1188', 'JS0599', '2026-04-30', '1101.02.1C.01.251197', '23淮投02', 829139.08);
INSERT INTO dws.am_pactasset_dws VALUES
('2021ZQJH1188', '2026-04-30', 'PACT-2021-001', '23苏华04', '251175');
INSERT INTO dws.am_projinvest_dws VALUES
('2021ZQJH1188', '2026-04-30', 'PACT-2021-001', 117177.50);

-- 3. 实收信托有误：a0001 与估值表资产一致，FA 4001 与 c1000 的差异等于主差异。
INSERT INTO dws.zf_detail_2024 VALUES
('2026-04-30', '2022XYZC0316', '华鑫信托-星耀资产配置服务信托', 783025546.65, 782908369.15, 250000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2022XYZC0316', '2026-04-30', '4001', '实收信托', 250117177.50);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202604-2022XYZC0316-01', '2026-04-30', '2022XYZC0316', '华鑫信托-星耀资产配置服务信托', 250000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2022XYZC0316', 'JS0599', '2026-04-30', '0004', '资产合计', 783025546.65),
('2022XYZC0316', 'JS0599', '2026-04-30', '1101.02.1C.01.251175', '23苏华04', 7893002.00);

-- 4. 负债及权益科目差异：c1000 与 4001 一致，非 1 开头科目组合能命中主差异。
INSERT INTO dws.zf_detail_2024 VALUES
('2026-04-30', '2023JHZX0666', '华鑫信托-嘉和甄选债券投资集合资金信托计划', 1000265019.18, 1000033409.18, 450000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2023JHZX0666', '2026-04-30', '4001', '实收信托', 450000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202604-2023JHZX0666-01', '2026-04-30', '2023JHZX0666', '华鑫信托-嘉和甄选债券投资集合资金信托计划', 450000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2023JHZX0666', 'JS0599', '2026-04-30', '0004', '资产合计', 1000265019.18),
('2023JHZX0666', 'JS0599', '2026-04-30', '2001.01', '应付管理费', 100000.00),
('2023JHZX0666', 'JS0599', '2026-04-30', '2203.01', '应付托管费', 131610.00),
('2023JHZX0666', 'JS0599', '2026-04-30', '1101.02.15.01.252302', '23苏进02', 231610.00);

-- 5. 负债及权益科目差异：主差异为负数，非 1 开头科目按金额绝对值命中，方向仍由主差异展示。
INSERT INTO dws.zf_detail_2024 VALUES
('2026-04-30', '2024HYLC0088', '华鑫信托-恒盈现金管理服务信托', 502345678.91, 502442222.12, 200000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2024HYLC0088', '2026-04-30', '4001', '实收信托', 200000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202604-2024HYLC0088-01', '2026-04-30', '2024HYLC0088', '华鑫信托-恒盈现金管理服务信托', 200000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2024HYLC0088', 'JS0599', '2026-04-30', '0004', '资产合计', 502345678.91),
('2024HYLC0088', 'JS0599', '2026-04-30', '2001.02', '应付销售服务费', 96543.21),
('2024HYLC0088', 'JS0599', '2026-04-30', '1002.01.01.01.44275001040030831', '中国农业银行股份有限公司', 50000.00);

-- 6. 暂无法确定：资产合计正确、c1000 正确、非 1 开头科目也无法命中差异。
INSERT INTO dws.zf_detail_2024 VALUES
('2026-04-30', '2024WJFW0999', '华鑫信托-稳健财富传承服务信托', 236801234.56, 236800234.56, 100000000.00);
INSERT INTO dws.fa_accountbalance_dws VALUES
('2024WJFW0999', '2026-04-30', '4001', '实收信托', 100000000.00);
INSERT INTO dws.currency_report_duration VALUES
('CRD-202604-2024WJFW0999-01', '2026-04-30', '2024WJFW0999', '华鑫信托-稳健财富传承服务信托', 100000000.00);
INSERT INTO dws.fa_valuationreport_dws VALUES
('2024WJFW0999', 'JS0599', '2026-04-30', '0004', '资产合计', 236801234.56),
('2024WJFW0999', 'JS0599', '2026-04-30', '2001.01', '应付管理费', 300.00),
('2024WJFW0999', 'JS0599', '2026-04-30', '2203.01', '应付托管费', 400.00);

CREATE INDEX zf_detail_2024_date_idx ON dws.zf_detail_2024 (caldate);
CREATE INDEX currency_report_duration_project_date_idx ON dws.currency_report_duration (c_projectcode, caldate);
CREATE INDEX fa_accountbalance_project_date_acc_idx ON dws.fa_accountbalance_dws (c_projcode, d_balancedate, c_accountcode);
CREATE INDEX fa_valuation_project_date_idx ON dws.fa_valuationreport_dws (c_projcode, d_valuationdate);
CREATE INDEX am_pactasset_project_date_asset_idx ON dws.am_pactasset_dws (c_projcode, d_cldate, c_udlyasset);
CREATE INDEX am_projinvest_project_date_pact_idx ON dws.am_projinvest_dws (c_projcode, d_cldate, c_pactid);
