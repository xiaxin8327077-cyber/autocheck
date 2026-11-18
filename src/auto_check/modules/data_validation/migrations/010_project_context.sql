ALTER TABLE data_validation_issues ADD COLUMN project_code TEXT NULL COMMENT '真实项目编号，旧记录未采集'
-- module-statement-break
ALTER TABLE data_validation_issues ADD COLUMN project_name TEXT NULL COMMENT '真实项目名称，缺失时不编造'
-- module-statement-break
ALTER TABLE data_validation_issues ADD COLUMN project_name_status VARCHAR(32) NOT NULL DEFAULT 'legacy_unavailable' COMMENT '项目名称定位状态，历史明细不可补造'
-- module-statement-break
ALTER TABLE data_validation_issues ADD COLUMN issue_kind VARCHAR(32) NOT NULL DEFAULT 'legacy' COMMENT '核查类型：缺值待核实与数值不符分开，历史类型未采集'
