CREATE SCHEMA IF NOT EXISTS dws;

CREATE TABLE IF NOT EXISTS dws.fa_accountbalance_dws (
  c_projcode varchar NULL,
  c_assetcode varchar NULL,
  d_balancedate date NULL,
  c_accountcode varchar NULL,
  c_accountname varchar NULL,
  f_balance numeric NULL,
  d_etltime timestamp NULL
);

CREATE INDEX IF NOT EXISTS fa_accountbalance_dws_proj_date_idx
  ON dws.fa_accountbalance_dws (c_projcode, d_balancedate);

CREATE INDEX IF NOT EXISTS fa_accountbalance_dws_proj_date_acc_idx
  ON dws.fa_accountbalance_dws (c_projcode, c_accountcode, d_balancedate);
