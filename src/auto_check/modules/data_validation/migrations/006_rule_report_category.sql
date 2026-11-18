ALTER TABLE data_validation_rules ADD COLUMN report_category VARCHAR(64) NOT NULL DEFAULT '' COMMENT '监管报送分类编码'
-- module-statement-break
CREATE INDEX ix_dv_rules_category ON data_validation_rules (report_category, id)
