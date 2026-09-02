CREATE TABLE report_special_processing_confirm_attachments (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '确认附件主键',
    record_id BIGINT NOT NULL COMMENT '关联特殊处理记录主键',
    audit_id BIGINT NOT NULL COMMENT '关联完成确认审计主键',
    sequence_no INT NOT NULL COMMENT '同一审计内图片顺序，1 至 3',
    content_type VARCHAR(64) NOT NULL COMMENT '图片 MIME 类型',
    byte_size INT NOT NULL COMMENT '图片字节数',
    content_sha256 CHAR(64) NOT NULL COMMENT '图片内容 SHA-256',
    content LONGBLOB NOT NULL COMMENT '图片原始字节，仅存储不解析',
    created_at DATETIME(6) NOT NULL COMMENT '写入时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_rsp_confirm_att_audit_seq (audit_id, sequence_no),
    KEY ix_rsp_confirm_att_record (record_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报表特殊处理确认说明图片附件'
