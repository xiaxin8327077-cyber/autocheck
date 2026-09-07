CREATE TABLE report_special_processing_record_attachments (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '记录附件主键',
    record_id BIGINT NOT NULL COMMENT '所属报表特殊处理记录主键',
    original_file_name VARCHAR(255) NOT NULL COMMENT '清理路径后的原文件名或生成名',
    file_extension VARCHAR(16) NOT NULL COMMENT '规范化小写扩展名',
    content_type VARCHAR(128) NOT NULL COMMENT '服务端确认后的 MIME 类型',
    byte_size INT NOT NULL COMMENT '原始字节数',
    content_sha256 CHAR(64) NOT NULL COMMENT '原始内容 SHA-256',
    content LONGBLOB NOT NULL COMMENT '原始文件字节，仅存储不解析不执行',
    created_by_user_id VARCHAR(64) NOT NULL COMMENT '添加人用户 ID',
    created_by_username_snapshot VARCHAR(100) NOT NULL COMMENT '添加人用户名快照',
    created_at DATETIME(6) NOT NULL COMMENT '添加时间',
    removed_by_user_id VARCHAR(64) NULL COMMENT '从当前集合移除的操作人用户 ID',
    removed_by_username_snapshot VARCHAR(100) NULL COMMENT '移除人用户名快照',
    removed_at DATETIME(6) NULL COMMENT '移除时间，NULL 表示当前附件',
    PRIMARY KEY (id),
    KEY ix_rsp_record_att_current (record_id, removed_at, created_at, id),
    KEY ix_rsp_record_att_hash (record_id, content_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='报表特殊处理记录附件，内容与元数据不可覆盖，移除为软删除'
