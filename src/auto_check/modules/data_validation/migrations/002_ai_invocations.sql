CREATE TABLE data_validation_ai_invocations (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '调用主键',
    operator_user_id VARCHAR(64) NOT NULL COMMENT '发起人',
    model_id VARCHAR(64) NOT NULL COMMENT '模型编号',
    model_name VARCHAR(200) NOT NULL COMMENT '模型显示名',
    prompt_version VARCHAR(64) NOT NULL COMMENT '提示词版本',
    tool_names VARCHAR(500) NOT NULL COMMENT '工具名',
    duration_ms INT NOT NULL COMMENT '耗时毫秒',
    error_code VARCHAR(64) NOT NULL COMMENT '错误码',
    created_at VARCHAR(32) NOT NULL COMMENT '时间',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据校验模型调用'
