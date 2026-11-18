ALTER TABLE data_validation_tasks ADD COLUMN report_period VARCHAR(10) NULL COMMENT '报送期'
-- module-statement-break
CREATE INDEX ix_dv_tasks_period ON data_validation_tasks (creator_user_id, report_period, id)
