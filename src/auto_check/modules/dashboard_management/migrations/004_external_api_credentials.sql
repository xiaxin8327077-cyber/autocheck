CREATE TABLE dashboard_management_external_api_credentials (
    scope_key VARCHAR(128) NOT NULL COMMENT '固定凭据作用域',
    token_digest CHAR(64) NOT NULL COMMENT 'SHA-256 十六进制摘要',
    token_fingerprint VARCHAR(16) NOT NULL COMMENT '非敏感短指纹',
    created_by VARCHAR(128) NOT NULL COMMENT '创建管理员标识',
    created_at DATETIME(6) NOT NULL COMMENT 'UTC 创建时间',
    updated_by VARCHAR(128) NOT NULL COMMENT '最近更新管理员标识',
    updated_at DATETIME(6) NOT NULL COMMENT 'UTC 最近更新时间',
    PRIMARY KEY (scope_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='看板外部接口专属 Token 凭据';
