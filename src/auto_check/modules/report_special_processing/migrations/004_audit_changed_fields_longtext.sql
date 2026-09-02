ALTER TABLE report_special_processing_audit_logs
    MODIFY COLUMN changed_fields_json LONGTEXT NOT NULL COMMENT '变更字段 JSON，处理脚本对照含完整原文供复制'
