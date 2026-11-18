CREATE TABLE data_validation_rules (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '规则主键',
    rule_code VARCHAR(32) NOT NULL COMMENT '规则编号',
    name VARCHAR(200) NOT NULL COMMENT '规则名称',
    description VARCHAR(1000) NOT NULL COMMENT '规则说明',
    creator_user_id VARCHAR(64) NOT NULL COMMENT '创建人',
    status VARCHAR(32) NOT NULL COMMENT '规则状态',
    current_version_id BIGINT NULL COMMENT '当前生效版本',
    source_id VARCHAR(64) NOT NULL COMMENT '数据源',
    table_name VARCHAR(128) NOT NULL COMMENT '目标表',
    rule_type VARCHAR(64) NOT NULL COMMENT '规则类型',
    updated_at VARCHAR(32) NOT NULL COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_dv_rules_code (rule_code),
    KEY ix_dv_rules_creator (creator_user_id, status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验规则'
-- module-statement-break
CREATE TABLE data_validation_rule_versions (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '版本主键',
    rule_id BIGINT NOT NULL COMMENT '规则主键',
    version_no INT NOT NULL COMMENT '版本号',
    definition_json LONGTEXT NOT NULL COMMENT '规则定义',
    sql_text LONGTEXT NOT NULL COMMENT '规则 SQL',
    mapping_version VARCHAR(64) NOT NULL COMMENT '映射版本',
    content_sha256 CHAR(64) NOT NULL COMMENT '内容哈希',
    generation_mode VARCHAR(16) NOT NULL COMMENT '生成方式',
    status VARCHAR(32) NOT NULL COMMENT '版本状态',
    created_at VARCHAR(32) NOT NULL COMMENT '创建时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_dv_versions (rule_id, version_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验规则版本'
-- module-statement-break
CREATE TABLE data_validation_settings (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '设置主键',
    source_allowlist_json LONGTEXT NOT NULL COMMENT '来源白名单',
    max_rules_per_task INT NOT NULL COMMENT '单任务规则上限',
    source_concurrency INT NOT NULL COMMENT '单源并发',
    rule_timeout_seconds INT NOT NULL COMMENT '单规则超时秒',
    task_timeout_seconds INT NOT NULL COMMENT '任务超时秒',
    issue_preview_limit INT NOT NULL COMMENT '明细预览上限',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验设置'
-- module-statement-break
CREATE TABLE data_validation_audit_logs (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '审计主键',
    rule_id BIGINT NULL COMMENT '规则主键',
    task_id BIGINT NULL COMMENT '任务主键',
    action_code VARCHAR(64) NOT NULL COMMENT '动作',
    operator_user_id VARCHAR(64) NOT NULL COMMENT '操作人',
    detail_json LONGTEXT NOT NULL COMMENT '详情',
    created_at VARCHAR(32) NOT NULL COMMENT '时间',
    PRIMARY KEY (id),
    KEY ix_dv_audit_rule (rule_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验审计'
