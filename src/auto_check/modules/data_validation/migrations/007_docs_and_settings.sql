CREATE TABLE IF NOT EXISTS data_validation_documents (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '文档主键',
    name VARCHAR(200) NOT NULL COMMENT '文档批次名称',
    file_name VARCHAR(255) NOT NULL COMMENT '原始文件名',
    content_sha256 CHAR(64) NOT NULL COMMENT '文档内容哈希',
    version_no INT NOT NULL COMMENT '版本号',
    status VARCHAR(16) NOT NULL COMMENT 'active/archived',
    table_count INT NOT NULL DEFAULT 0 COMMENT '表数量',
    field_count INT NOT NULL DEFAULT 0 COMMENT '字段数量',
    warnings_json LONGTEXT NULL COMMENT '解析告警',
    imported_by VARCHAR(64) NOT NULL COMMENT '导入人',
    imported_at VARCHAR(32) NOT NULL COMMENT '导入时间',
    activated_at VARCHAR(32) NULL COMMENT '启用时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_dv_doc_version (version_no),
    KEY ix_dv_doc_status (status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验文档快照'
-- module-statement-break
CREATE TABLE IF NOT EXISTS data_validation_doc_tables (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '文档表主键',
    document_id BIGINT NOT NULL COMMENT '文档主键',
    data_source_name VARCHAR(128) NOT NULL COMMENT '归属数据源名称',
    table_name VARCHAR(128) NOT NULL COMMENT '表英文名',
    table_name_cn VARCHAR(255) NOT NULL COMMENT '表中文名',
    sheet_name VARCHAR(200) NOT NULL COMMENT '来源 sheet',
    source_desc TEXT NULL COMMENT '数据来源说明',
    dimension VARCHAR(128) NULL COMMENT '维度',
    period VARCHAR(64) NULL COMMENT '采集周期',
    scope TEXT NULL COMMENT '数据范围',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序',
    PRIMARY KEY (id),
    KEY ix_dv_doc_tables_doc (document_id, data_source_name),
    KEY ix_dv_doc_tables_name (document_id, table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档表清单'
-- module-statement-break
CREATE TABLE IF NOT EXISTS data_validation_doc_fields (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '字段主键',
    table_id BIGINT NOT NULL COMMENT '文档表主键',
    field_name VARCHAR(128) NOT NULL COMMENT '字段英文名',
    field_cn VARCHAR(255) NULL COMMENT '字段中文名',
    data_type VARCHAR(64) NULL COMMENT '字段类型',
    is_pk VARCHAR(1) NULL COMMENT '是否主键 Y/空',
    nullable VARCHAR(8) NULL COMMENT '能否为空 Y/N/空',
    default_value VARCHAR(255) NULL COMMENT '默认值',
    dictionary TEXT NULL COMMENT '字典',
    logic TEXT NULL COMMENT '取数逻辑',
    source_table VARCHAR(200) NULL COMMENT '来源表',
    source_field VARCHAR(128) NULL COMMENT '来源字段',
    source_field_cn VARCHAR(255) NULL COMMENT '来源字段中文名',
    source_table_cn VARCHAR(255) NULL COMMENT '来源表中文名',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '排序',
    PRIMARY KEY (id),
    KEY ix_dv_doc_fields_table (table_id, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档字段清单'
-- module-statement-break
CREATE TABLE IF NOT EXISTS data_validation_prompt_templates (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '提示词主键',
    stage VARCHAR(32) NOT NULL COMMENT 'select_table/generate_rule/generate_sql',
    content LONGTEXT NOT NULL COMMENT '提示词内容',
    version_no INT NOT NULL COMMENT '版本号',
    is_active TINYINT NOT NULL DEFAULT 1 COMMENT '是否启用',
    updated_by VARCHAR(64) NOT NULL COMMENT '更新人',
    updated_at VARCHAR(32) NOT NULL COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY ix_dv_prompts_stage (stage, is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验提示词模板'
-- module-statement-break
CREATE TABLE IF NOT EXISTS data_validation_doc_source_rules (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '规则主键',
    sheet_prefix VARCHAR(128) NOT NULL COMMENT 'sheet 名前缀',
    data_source_name VARCHAR(128) NOT NULL COMMENT '归属数据源名称',
    sort_order INT NOT NULL DEFAULT 0 COMMENT '优先级',
    PRIMARY KEY (id),
    KEY ix_dv_source_rules_prefix (sheet_prefix, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档 sheet 到数据源映射规则'