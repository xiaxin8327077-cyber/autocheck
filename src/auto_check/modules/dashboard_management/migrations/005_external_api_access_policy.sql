CREATE TABLE dashboard_management_external_api_access_policies (
    scope_key VARCHAR(128) NOT NULL COMMENT '固定外部接口作用域',
    whitelist_enabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否启用 IP 白名单',
    allowed_ips_json TEXT NOT NULL COMMENT '规范化 IP 地址 JSON 数组',
    created_by VARCHAR(128) NOT NULL COMMENT '创建管理员标识',
    created_at DATETIME(6) NOT NULL COMMENT 'UTC 创建时间',
    updated_by VARCHAR(128) NOT NULL COMMENT '最近更新管理员标识',
    updated_at DATETIME(6) NOT NULL COMMENT 'UTC 最近更新时间',
    PRIMARY KEY (scope_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='看板外部接口 IP 白名单策略';
