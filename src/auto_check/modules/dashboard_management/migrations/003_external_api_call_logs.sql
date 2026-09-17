CREATE TABLE dashboard_management_external_api_calls (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '外部接口调用记录主键',
    called_at DATETIME(6) NOT NULL COMMENT 'UTC 调用开始时间',
    board_code VARCHAR(64) NOT NULL COMMENT '固定看板编码',
    http_status INT NOT NULL COMMENT '最终 HTTP 状态码',
    result_status VARCHAR(16) NOT NULL COMMENT 'success partial 或 error',
    failed_region_count INT NOT NULL DEFAULT 0 COMMENT '失败区域数量',
    duration_ms BIGINT NOT NULL COMMENT '调用耗时毫秒',
    request_id VARCHAR(64) NOT NULL COMMENT '接口请求追踪号',
    caller_ip VARCHAR(45) NOT NULL COMMENT 'TCP 对端 IPv4 或 IPv6',
    error_code VARCHAR(64) NULL COMMENT '安全错误码',
    error_message VARCHAR(500) NULL COMMENT '安全错误摘要',
    PRIMARY KEY (id),
    UNIQUE KEY uq_dashboard_management_external_api_calls_request_id (request_id),
    KEY ix_dashboard_management_external_api_calls_called_at (called_at),
    KEY ix_dashboard_management_external_api_calls_board_time (board_code, called_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='看板外部接口调用记录';
