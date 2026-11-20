ALTER TABLE data_validation_issues ADD COLUMN query_result_json TEXT NULL COMMENT '规则执行时实际选取的查询列和值'
-- module-statement-break
ALTER TABLE data_validation_task_rules
    ADD COLUMN source_name TEXT NULL COMMENT '批次受理时的数据源名称',
    ADD COLUMN table_name_cn TEXT NULL COMMENT '批次受理时的目标表中文名',
    ADD COLUMN report_category_name TEXT NULL COMMENT '批次受理时的报送分类名称',
    ADD COLUMN execution_generation INT NOT NULL DEFAULT 0 COMMENT '重试领取时递增，阻止旧执行发布结果'
