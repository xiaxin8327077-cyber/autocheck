-- 2026-07-10 acceptance data for the PBC row-level database validation engine.
-- This script creates a compact PostgreSQL fixture for ZG table reads, field mapping metadata,
-- public information checks, template checks, previous-period tables, and a ZG07 decrypt fallback.

CREATE SCHEMA IF NOT EXISTS dws;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.proname = 'decrypt'
      AND pg_get_function_arguments(p.oid) = 'data bytea, key text, method text'
  ) THEN
    CREATE FUNCTION public.decrypt(data bytea, key text, method text)
    RETURNS bytea
    LANGUAGE sql
    IMMUTABLE
    AS 'SELECT data';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS dws.xt_reg_table_baseinfo (
  id varchar PRIMARY KEY,
  table_name_en varchar NOT NULL,
  table_name_zh varchar,
  sys_manage_id varchar,
  classification_id varchar
);

CREATE TABLE IF NOT EXISTS dws.xt_reg_table_field_info (
  table_id varchar NOT NULL,
  field_propert varchar NOT NULL,
  field_name varchar NOT NULL,
  sort integer
);

CREATE TABLE IF NOT EXISTS dws.public_information_rh (
  projcode varchar,
  productcode varchar,
  projname varchar,
  startdate varchar,
  projbegdate varchar,
  predate varchar,
  projpredate varchar,
  issuerorgcode varchar,
  jgcode varchar,
  infotype varchar
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_baseinfo_zg01_26 (
  projcode varchar,
  projname varchar,
  issuername varchar,
  issuerorgcode varchar,
  projpredate varchar,
  earlystopflg varchar,
  creditflg varchar,
  creditform varchar,
  credittype varchar,
  runmode varchar,
  redeemflg varchar,
  raisebegdate varchar,
  levelflg varchar,
  source varchar,
  depoutorgcode varchar,
  depinorgcode varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_begraiseinfo_zg02_26 (
  projcode varchar,
  areacode varchar,
  clientkind varchar,
  moneytype varchar,
  raiseamt varchar,
  raiseamtcny varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_projendinfo_zg03_26 (
  projcode varchar,
  moneytype varchar,
  clientincomecny varchar,
  clientrate varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_projholdinfo_zg04 (
  projcode varchar,
  areacode varchar,
  clientkind varchar,
  moneytype varchar,
  projshare varchar,
  curraiseshare varchar,
  curcashshare varchar,
  projamt varchar,
  projamtcny varchar,
  currraiseamt varchar,
  curcashamt varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_projdebt_zg05_2024 (
  projcode varchar,
  moneytype varchar,
  datetype varchar,
  a5100 varchar,
  a7100 varchar,
  a0000 varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_beneficial_zg06 (
  projcode varchar,
  beneficialcode varchar,
  issuername varchar,
  issuercode varchar,
  begdate varchar,
  predate varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_ioudetail_zg07 (
  projcode varchar,
  ioucode varchar,
  loantype varchar,
  debtortype varchar,
  debtorcode bytea,
  areacode varchar,
  indutry varchar,
  enscale varchar,
  rateinfo varchar,
  grantdate varchar,
  enddate varchar,
  perioddate varchar,
  iouamtcny varchar,
  iouamtcny_tz varchar,
  loanissuerareacode varchar,
  loanstate varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_spvdetail_zg08 (
  projcode varchar,
  riverprojcode varchar,
  riverprojtype varchar,
  debtorproj varchar,
  sharamtcny varchar,
  enddate varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_debtordate_zg09 (
  issuercode varchar,
  cpkj varchar,
  fb00001 varchar,
  fb00002 varchar,
  g001a varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_surecinfo_zg10 (
  issuercode varchar,
  cpkj varchar,
  projtype varchar,
  fb00001 varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_industinfo_zg11 (
  projcode varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgzgzh_zg12 (
  projcode varchar,
  innercode varchar,
  zqcode varchar,
  jkrtype varchar,
  areacode varchar,
  jkrid varchar,
  industry varchar,
  qygm varchar,
  startdate varchar,
  predate varchar,
  lsp varchar,
  zqtype varchar,
  djplace varchar,
  djcode varchar,
  danbaotype varchar,
  zqye varchar,
  zqyecny varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.zgzgzh_zg13 (
  projcode varchar,
  innercode varchar,
  targetcode varchar,
  targetname varchar,
  cgbl varchar,
  predate varchar,
  a7310 varchar,
  a7320 varchar,
  caldate date
);

CREATE TABLE IF NOT EXISTS dws.balance_sheet_info (
  field_name varchar,
  field_value varchar
);

CREATE TABLE IF NOT EXISTS dws.balance_sheet_info_zcglxt (
  field_name varchar,
  field_value varchar
);

CREATE TABLE IF NOT EXISTS dws.balance_sheet_info2 (
  field_name varchar,
  field_value varchar
);

CREATE TABLE IF NOT EXISTS dws.balance_sheet_info2_zcglxt (
  field_name varchar,
  field_value varchar
);

CREATE TABLE IF NOT EXISTS dws.zgxgzh_baseinfo_zg01_26_2026_06 (LIKE dws.zgxgzh_baseinfo_zg01_26 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_begraiseinfo_zg02_26_2026_06 (LIKE dws.zgxgzh_begraiseinfo_zg02_26 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_projendinfo_zg03_26_2026_06 (LIKE dws.zgxgzh_projendinfo_zg03_26 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_projholdinfo_zg04_2026_06 (LIKE dws.zgxgzh_projholdinfo_zg04 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_projdebt_zg05_2024_2026_06 (LIKE dws.zgxgzh_projdebt_zg05_2024 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_beneficial_zg06_2026_06 (LIKE dws.zgxgzh_beneficial_zg06 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_ioudetail_zg07_2026_06 (LIKE dws.zgxgzh_ioudetail_zg07 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_spvdetail_zg08_2026_06 (LIKE dws.zgxgzh_spvdetail_zg08 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_debtordate_zg09_2026_06 (LIKE dws.zgxgzh_debtordate_zg09 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_surecinfo_zg10_2026_06 (LIKE dws.zgxgzh_surecinfo_zg10 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgxgzh_industinfo_zg11_2026_06 (LIKE dws.zgxgzh_industinfo_zg11 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgzgzh_zg12_2026_06 (LIKE dws.zgzgzh_zg12 INCLUDING ALL);
CREATE TABLE IF NOT EXISTS dws.zgzgzh_zg13_2026_06 (LIKE dws.zgzgzh_zg13 INCLUDING ALL);

BEGIN;

DELETE FROM dws.xt_reg_table_field_info WHERE table_id LIKE 'AC20260710_%';
DELETE FROM dws.xt_reg_table_baseinfo WHERE id LIKE 'AC20260710_%';
DELETE FROM dws.public_information_rh WHERE projcode LIKE 'DBV20260710%' OR productcode LIKE 'DBV20260710%';
DELETE FROM dws.balance_sheet_info WHERE field_name IN ('A_g00100', 'fb00001', 'fb00002');
DELETE FROM dws.balance_sheet_info_zcglxt WHERE field_name IN ('A_g00100', 'fb00001', 'fb00002');
DELETE FROM dws.balance_sheet_info2 WHERE field_name IN ('A_g00100', 'fb00001', 'fb00002');
DELETE FROM dws.balance_sheet_info2_zcglxt WHERE field_name IN ('A_g00100', 'fb00001', 'fb00002');

DELETE FROM dws.zgxgzh_baseinfo_zg01_26 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_begraiseinfo_zg02_26 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_projendinfo_zg03_26 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_projholdinfo_zg04 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_projdebt_zg05_2024 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_beneficial_zg06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_ioudetail_zg07 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_spvdetail_zg08 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_debtordate_zg09 WHERE caldate = DATE '2026-07-10' AND issuercode = 'D1003632000013';
DELETE FROM dws.zgxgzh_surecinfo_zg10 WHERE caldate = DATE '2026-07-10' AND issuercode = 'D1003632000013';
DELETE FROM dws.zgxgzh_industinfo_zg11 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgzgzh_zg12 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgzgzh_zg13 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_baseinfo_zg01_26_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_begraiseinfo_zg02_26_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_projendinfo_zg03_26_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_projholdinfo_zg04_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_projdebt_zg05_2024_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_beneficial_zg06_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_ioudetail_zg07_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_spvdetail_zg08_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgxgzh_debtordate_zg09_2026_06 WHERE caldate = DATE '2026-06-30' AND issuercode = 'D1003632000013';
DELETE FROM dws.zgxgzh_surecinfo_zg10_2026_06 WHERE caldate = DATE '2026-06-30' AND issuercode = 'D1003632000013';
DELETE FROM dws.zgxgzh_industinfo_zg11_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgzgzh_zg12_2026_06 WHERE projcode LIKE 'DBV20260710%';
DELETE FROM dws.zgzgzh_zg13_2026_06 WHERE projcode LIKE 'DBV20260710%';

INSERT INTO dws.xt_reg_table_baseinfo(id, table_name_en, table_name_zh, sys_manage_id, classification_id) VALUES
('AC20260710_ZG01', 'zgxgzh_baseinfo_zg01_26', '资管产品基本信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG02', 'zgxgzh_begraiseinfo_zg02_26', '资管产品初始募集信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG03', 'zgxgzh_projendinfo_zg03_26', '资管产品终止信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG04', 'zgxgzh_projholdinfo_zg04', '资管产品存续募集信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG05', 'zgxgzh_projdebt_zg05_2024', '资管产品资产负债信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG06', 'zgxgzh_beneficial_zg06', '资产收益权明细信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG07', 'zgxgzh_ioudetail_zg07', '贷款明细信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG08', 'zgxgzh_spvdetail_zg08', '特定目的载体交易对手明细信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG09', 'zgxgzh_debtordate_zg09', '资产负债剩余期限信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG10', 'zgxgzh_surecinfo_zg10', '债券等资产配置情况信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG11', 'zgxgzh_industinfo_zg11', '产业投向信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG12', 'zgzgzh_zg12', '除资产收益权外其他债权明细信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_ZG13', 'zgzgzh_zg13', '其他股权投资明细信息', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_TPL1', 'balance_sheet_info', '资产负债表模板', 'DBV20260710', 'ACCEPTANCE'),
('AC20260710_TPL2', 'balance_sheet_info2', '债券资产配置模板', 'DBV20260710', 'ACCEPTANCE');

INSERT INTO dws.xt_reg_table_field_info(table_id, field_propert, field_name, sort) VALUES
('AC20260710_ZG01', 'projcode', '产品代码', 1),
('AC20260710_ZG01', 'projname', '产品名称', 2),
('AC20260710_ZG01', 'issuername', '发行机构名称', 3),
('AC20260710_ZG05', 'projcode', '产品代码', 1),
('AC20260710_ZG05', 'moneytype', '币种', 2),
('AC20260710_ZG05', 'datetype', '数据类型', 3),
('AC20260710_ZG05', 'a5100', 'A5100_除回购和拆借外贷款', 4),
('AC20260710_ZG07', 'projcode', '产品代码', 1),
('AC20260710_ZG07', 'debtorcode', '借款人代码', 2),
('AC20260710_ZG07', 'iouamtcny', '贷款余额折人民币', 3),
('AC20260710_ZG09', 'issuercode', '金融机构编码', 1),
('AC20260710_ZG10', 'issuercode', '金融机构编码', 1),
('AC20260710_ZG12', 'projcode', '产品代码', 1),
('AC20260710_ZG12', 'jkrid', '借款人代码', 2);

INSERT INTO dws.public_information_rh VALUES
('DBV20260710P001', 'DBV20260710P001', '逐笔验收产品1号', '2026-01-01', '2026-01-01', '2026-12-31', '2026-12-31', 'D1003632000013', 'D1003632000013', '新增资管产品基本信息');

INSERT INTO dws.zgxgzh_baseinfo_zg01_26 VALUES
('DBV20260710P001', 'A?', '江苏省国际信托有限责任公司', 'D1003632000013', '', '1', '1', '1', '1', '1', '1', '20250101', '1', '2', '中国银行南京分行', '', DATE '2026-07-10');

INSERT INTO dws.zgxgzh_begraiseinfo_zg02_26 VALUES
('DBV20260710P001', '320000', '6', 'CNY', '1000', '900', DATE '2026-07-10');

INSERT INTO dws.zgxgzh_projendinfo_zg03_26 VALUES
('DBV20260710P001', 'CNY', '600000000', '12%', DATE '2026-07-10');

INSERT INTO dws.zgxgzh_projholdinfo_zg04 VALUES
('DBV20260710P001', '320000', '2', 'CNY', '900', '100', '50', '9000000', '900', '1000000', '500000', DATE '2026-07-10');
INSERT INTO dws.zgxgzh_projholdinfo_zg04_2026_06 VALUES
('DBV20260710P001', '320000', '2', 'CNY', '1000', '0', '0', '10000000', '1000', '0', '0', DATE '2026-06-30');

INSERT INTO dws.zgxgzh_projdebt_zg05_2024 VALUES
('DBV20260710P001', 'BWB', '3', '1000000', '500000', '1500000', DATE '2026-07-10'),
('DBV20260710P001', 'CNY', '1', '900000', '500000', '1400000', DATE '2026-07-10');
INSERT INTO dws.zgxgzh_projdebt_zg05_2024_2026_06 VALUES
('DBV20260710P001', 'BWB', '3', '800000', '300000', '1100000', DATE '2026-06-30');

INSERT INTO dws.zgxgzh_beneficial_zg06 VALUES
('DBV20260710P001', 'BEN2026071001', '异常出让机构', 'BADCODE', '2025-12-01', '2027-02-01', DATE '2026-07-10');
INSERT INTO dws.zgxgzh_beneficial_zg06_2026_06 VALUES
('DBV20260710P001', 'BEN2026071001', '异常出让机构', 'BADCODE', '2026-01-01', '2026-11-01', DATE '2026-06-30');

INSERT INTO dws.zgxgzh_ioudetail_zg07 VALUES
('DBV20260710P001', 'IOU2026071001', '1', '2', convert_to(encode(convert_to('BADCODE', 'UTF8'), 'hex'), 'UTF8'), '320000', '1', '', '0.5', '2026-07-10', '2027-02-01', '2027-03-01', '600000', '600000', '320000', '1', DATE '2026-07-10');
INSERT INTO dws.zgxgzh_ioudetail_zg07_2026_06 VALUES
('DBV20260710P001', 'IOU2026071001', '1', '2', convert_to(encode(convert_to('OLDVALUE', 'UTF8'), 'hex'), 'UTF8'), '320102', '3', '2', '5', '2026-06-10', '2026-12-01', '2026-12-01', '400000', '400000', '320102', '1', DATE '2026-06-30');

INSERT INTO dws.zgxgzh_spvdetail_zg08 VALUES
('DBV20260710P001', 'DBV20260710CP01', '1', 'A7100', '100000', '2027-01-31', DATE '2026-07-10');

INSERT INTO dws.zgxgzh_debtordate_zg09 VALUES
('D1003632000013', '1', '10000', '20000', '30000', DATE '2026-07-10');

INSERT INTO dws.zgxgzh_surecinfo_zg10 VALUES
('D1003632000013', '1', '1', '10000', DATE '2026-07-10');

INSERT INTO dws.zgzgzh_zg12 VALUES
('DBV20260710P001', 'ZQ2026071001', 'ZQ2026071001', '2', '320000', '', '1', '', '2026-07-10', '2090-01-01', '0.5', '1', '异常场所', 'BAD', '1', '1000000', '1000000', DATE '2026-07-10');
INSERT INTO dws.zgzgzh_zg12_2026_06 VALUES
('DBV20260710P001', 'ZQ2026071001', 'ZQ2026071001', '2', '320102', 'OLD-CODE', '3', '2', '2026-06-10', '2026-12-31', '5', '1', '正常场所', '123456', '1', '1000000', '1000000', DATE '2026-06-30');

INSERT INTO dws.zgzgzh_zg13 VALUES
('DBV20260710P001', 'EQ2026071001', 'BADTARGET', '异常标的企业', '10', '2027-02-01', '100000', '200000', DATE '2026-07-10');

INSERT INTO dws.balance_sheet_info VALUES
('A_g00100', '1000'),
('fb00001', '2000'),
('fb00002', '3000');
INSERT INTO dws.balance_sheet_info_zcglxt VALUES
('A_g00100', '1000');
INSERT INTO dws.balance_sheet_info2 VALUES
('fb00001', '2000');
INSERT INTO dws.balance_sheet_info2_zcglxt VALUES
('fb00001', '2000');

COMMIT;
