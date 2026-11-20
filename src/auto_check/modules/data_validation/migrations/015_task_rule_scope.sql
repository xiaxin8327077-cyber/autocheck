ALTER TABLE data_validation_task_rules
    ADD COLUMN report_category VARCHAR(64) NULL COMMENT '受理时冻结的报送分类，历史快照按原版本读取',
    ADD COLUMN source_id VARCHAR(64) NULL COMMENT '受理时冻结的数据源编号，历史快照按原版本读取'
