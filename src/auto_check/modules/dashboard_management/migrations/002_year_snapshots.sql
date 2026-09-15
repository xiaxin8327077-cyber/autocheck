CREATE TABLE dashboard_management_year_snapshots (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '年度趋势快照主键',
    region_id BIGINT NOT NULL COMMENT '数据区域主键',
    period_year INT NOT NULL COMMENT '自然年',
    period_type VARCHAR(16) NOT NULL COMMENT '周期类型：month 或 quarter',
    period_value INT NOT NULL COMMENT '月份 1 至 12 或季度 1 至 4',
    row_json LONGTEXT NOT NULL COMMENT '该周期完整结果 JSON',
    source_refreshed_at DATETIME(6) NULL COMMENT '来源最近成功刷新时间',
    created_at DATETIME(6) NOT NULL COMMENT '创建时间',
    updated_at DATETIME(6) NOT NULL COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_dashboard_management_year_snapshot_period (region_id, period_year, period_type, period_value),
    KEY ix_dashboard_management_year_snapshots_region_year (region_id, period_year, period_value),
    CONSTRAINT fk_dashboard_management_year_snapshots_region FOREIGN KEY (region_id) REFERENCES dashboard_management_regions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='看板年度趋势快照'
