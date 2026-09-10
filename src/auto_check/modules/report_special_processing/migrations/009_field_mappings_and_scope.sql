-- 报表特殊处理录入：处理表“处理范围（项目/合同）”与字段定位映射配置。
-- 1) 每张处理表增加项目/合同处理范围（结构化内容内保存解析后的项目/合同值列表）；
-- 2) 生成处理脚本时需按“数据源+schema+表名”找到项目字段与合同字段（project_field / contract_field），
--    未配置映射时禁止生成 UPDATE，避免猜测数据库字段名；
-- 3) 映射配置保存在本表，可通过模块接口维护，不落在特殊处理页面。
CREATE TABLE IF NOT EXISTS report_special_processing_field_mappings (
    id BIGINT NOT NULL AUTO_INCREMENT,
    datasource_id VARCHAR(64) NOT NULL COMMENT '系统已配置数据源ID',
    schema_name VARCHAR(128) NOT NULL DEFAULT '' COMMENT '数据库架构名（PostgreSQL 的 schema；MySQL 为库名），与结构化内容 schema 一致',
    table_name VARCHAR(128) NOT NULL COMMENT '真实物理表名',
    project_field VARCHAR(128) NOT NULL DEFAULT '' COMMENT '项目定位字段列名（如 project_code），为空表示未配置',
    contract_field VARCHAR(128) NOT NULL DEFAULT '' COMMENT '合同定位字段列名（如 contract_no），为空表示未配置',
    updated_by_user_id VARCHAR(64) NULL COMMENT '最后维护人用户ID',
    updated_by_username_snapshot VARCHAR(100) NULL COMMENT '最后维护人用户名快照',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '最后更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_rsp_field_mapping (datasource_id, schema_name, table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报表特殊处理：表级项目/合同定位字段映射配置，未配置时禁止生成处理脚本';