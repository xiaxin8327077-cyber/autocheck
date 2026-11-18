CREATE TABLE data_validation_tasks (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '任务主键',
    creator_user_id VARCHAR(64) NOT NULL COMMENT '发起人',
    source_id VARCHAR(64) NOT NULL COMMENT '数据源',
    status VARCHAR(32) NOT NULL COMMENT '任务状态',
    params_json LONGTEXT NOT NULL COMMENT '参数快照',
    truncated INT NOT NULL COMMENT '是否截断',
    created_at VARCHAR(32) NOT NULL COMMENT '时间',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验任务'
-- module-statement-break
CREATE TABLE data_validation_task_rules (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '任务规则主键',
    task_id BIGINT NOT NULL COMMENT '任务主键',
    rule_id BIGINT NOT NULL COMMENT '规则主键',
    version_id BIGINT NOT NULL COMMENT '版本主键',
    version_no INT NOT NULL COMMENT '版本号',
    content_sha256 CHAR(64) NOT NULL COMMENT '内容哈希',
    sql_summary VARCHAR(180) NOT NULL COMMENT 'SQL 摘要',
    status VARCHAR(32) NOT NULL COMMENT '执行状态',
    violation_count INT NOT NULL COMMENT '违规条数',
    truncated INT NOT NULL COMMENT '是否截断',
    error_code VARCHAR(64) NOT NULL COMMENT '错误码',
    PRIMARY KEY (id),
    KEY ix_dv_task_rules (task_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验任务规则'
-- module-statement-break
CREATE TABLE data_validation_issues (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '异常主键',
    task_id BIGINT NOT NULL COMMENT '任务主键',
    rule_id BIGINT NOT NULL COMMENT '规则主键',
    version_no INT NOT NULL COMMENT '版本号',
    business_key VARCHAR(200) NOT NULL COMMENT '业务键',
    message VARCHAR(500) NOT NULL COMMENT '异常说明',
    created_at VARCHAR(32) NOT NULL COMMENT '时间',
    PRIMARY KEY (id),
    KEY ix_dv_issues_task (task_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验异常明细'
