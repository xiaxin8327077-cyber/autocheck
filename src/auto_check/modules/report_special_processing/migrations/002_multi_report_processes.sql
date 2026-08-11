ALTER TABLE report_special_processing_records
    MODIFY COLUMN report_process_name_snapshot VARCHAR(500) NOT NULL COMMENT '报送流程名称快照（多选时顿号拼接）'
-- module-statement-break
CREATE TABLE IF NOT EXISTS report_special_processing_processes (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '关联报送明细主键',
    record_id BIGINT NOT NULL COMMENT '关联特殊处理记录主键',
    sequence_no INT NOT NULL COMMENT '报送显示顺序',
    report_process_code VARCHAR(64) NOT NULL COMMENT '报送流程编码',
    report_process_name_snapshot VARCHAR(100) NOT NULL COMMENT '报送流程名称快照',
    created_at DATETIME(6) NOT NULL COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_rsp_processes_sequence (record_id, sequence_no),
    UNIQUE KEY uq_rsp_processes_code (record_id, report_process_code),
    KEY ix_rsp_processes_record (record_id),
    KEY ix_rsp_processes_code (report_process_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报表特殊处理关联报送明细表'
