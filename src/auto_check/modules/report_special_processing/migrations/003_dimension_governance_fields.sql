ALTER TABLE report_special_processing_records
    ADD COLUMN dimension VARCHAR(16) NULL COMMENT '所属维度 project/fund/asset/finance' AFTER report_period,
    ADD COLUMN governance_owner_user_id VARCHAR(64) NULL COMMENT '数据治理负责人用户ID' AFTER handler_display_name_snapshot,
    ADD COLUMN governance_owner_username_snapshot VARCHAR(64) NULL COMMENT '数据治理负责人用户名快照' AFTER governance_owner_user_id,
    ADD COLUMN governance_owner_display_name_snapshot VARCHAR(64) NULL COMMENT '数据治理负责人显示名快照' AFTER governance_owner_username_snapshot,
    ADD COLUMN table_name VARCHAR(128) NULL COMMENT '处理表名' AFTER summary,
    ADD COLUMN field_name VARCHAR(128) NULL COMMENT '处理字段名' AFTER table_name,
    ADD COLUMN value_before VARCHAR(500) NULL COMMENT '修改前' AFTER field_name,
    ADD COLUMN value_after VARCHAR(500) NULL COMMENT '修改后' AFTER value_before
