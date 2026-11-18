CREATE TABLE data_validation_test_cases (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '案例主键',
    rule_id BIGINT NOT NULL COMMENT '规则主键',
    version_no INT NOT NULL COMMENT '版本号',
    case_name VARCHAR(64) NOT NULL COMMENT '案例名',
    input_json LONGTEXT NOT NULL COMMENT '输入样本',
    expected_count INT NOT NULL COMMENT '期望条数',
    actual_count INT NOT NULL COMMENT '实际条数',
    status VARCHAR(16) NOT NULL COMMENT '测试状态',
    created_at VARCHAR(32) NOT NULL COMMENT '时间',
    PRIMARY KEY (id),
    KEY ix_dv_cases_rule (rule_id, version_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验测试案例'
-- module-statement-break
CREATE TABLE data_validation_confirmations (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '确认主键',
    rule_id BIGINT NOT NULL COMMENT '规则主键',
    version_no INT NOT NULL COMMENT '版本号',
    version_id BIGINT NOT NULL COMMENT '版本主键',
    content_sha256 CHAR(64) NOT NULL COMMENT '内容哈希',
    confirmer_user_id VARCHAR(64) NOT NULL COMMENT '确认人',
    passed_count INT NOT NULL COMMENT '通过数',
    failed_count INT NOT NULL COMMENT '失败数',
    not_run_count INT NOT NULL COMMENT '未运行数',
    created_at VARCHAR(32) NOT NULL COMMENT '时间',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验确认记录'
