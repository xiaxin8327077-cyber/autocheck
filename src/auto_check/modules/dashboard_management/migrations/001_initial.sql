CREATE TABLE dashboard_management_regions (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '数据区域主键',
    board_code VARCHAR(64) NOT NULL COMMENT '固定看板编码',
    region_code VARCHAR(64) NOT NULL COMMENT '稳定数据区域编码',
    name VARCHAR(100) NOT NULL COMMENT '数据区域名称',
    shape VARCHAR(16) NOT NULL COMMENT '数据形态：scalar 或 list',
    built_in TINYINT(1) NOT NULL COMMENT '是否内置目录',
    enabled TINYINT(1) NOT NULL COMMENT '是否启用',
    system_supported TINYINT(1) NOT NULL COMMENT '是否支持系统数据',
    default_mode VARCHAR(16) NOT NULL COMMENT '默认来源模式',
    display_order INT NOT NULL COMMENT '显示顺序',
    description VARCHAR(500) NOT NULL COMMENT '数据区域说明',
    created_at DATETIME(6) NOT NULL COMMENT '创建时间',
    updated_at DATETIME(6) NOT NULL COMMENT '更新时间',
    row_version BIGINT NOT NULL COMMENT '乐观锁版本号',
    PRIMARY KEY (id),
    UNIQUE KEY uq_dashboard_management_region_code (region_code),
    KEY ix_dashboard_management_regions_board_order (board_code, display_order, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='看板管理数据区域'
-- module-statement-break
CREATE TABLE dashboard_management_fields (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT '字段主键',
    region_id BIGINT NOT NULL COMMENT '数据区域主键',
    field_alias VARCHAR(64) NOT NULL COMMENT '稳定字段别名',
    name VARCHAR(100) NOT NULL COMMENT '字段显示名',
    value_type VARCHAR(16) NOT NULL COMMENT '字段值类型',
    nullable TINYINT(1) NOT NULL COMMENT '是否允许空值',
    built_in TINYINT(1) NOT NULL COMMENT '是否内置字段',
    enabled TINYINT(1) NOT NULL COMMENT '是否启用',
    display_order INT NOT NULL COMMENT '显示顺序',
    description VARCHAR(500) NOT NULL COMMENT '字段说明',
    created_at DATETIME(6) NOT NULL COMMENT '创建时间',
    updated_at DATETIME(6) NOT NULL COMMENT '更新时间',
    row_version BIGINT NOT NULL COMMENT '乐观锁版本号',
    PRIMARY KEY (id),
    UNIQUE KEY uq_dashboard_management_field_alias (region_id, field_alias),
    KEY ix_dashboard_management_fields_region_order (region_id, display_order, id),
    CONSTRAINT fk_dashboard_management_fields_region FOREIGN KEY (region_id) REFERENCES dashboard_management_regions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='看板管理区域字段'
-- module-statement-break
CREATE TABLE dashboard_management_source_configs (
    region_id BIGINT NOT NULL COMMENT '数据区域主键',
    source_mode VARCHAR(16) NOT NULL COMMENT '来源模式：system 或 sql',
    datasource_id VARCHAR(64) NULL COMMENT 'SQL 数据源标识',
    sql_text LONGTEXT NULL COMMENT '只读 SQL 文本',
    tested_signature CHAR(64) NULL COMMENT '最近成功测试摘要',
    tested_at DATETIME(6) NULL COMMENT '最近成功测试时间',
    tested_by VARCHAR(64) NULL COMMENT '最近测试用户标识',
    created_at DATETIME(6) NOT NULL COMMENT '创建时间',
    updated_at DATETIME(6) NOT NULL COMMENT '更新时间',
    row_version BIGINT NOT NULL COMMENT '乐观锁版本号',
    PRIMARY KEY (region_id),
    CONSTRAINT fk_dashboard_management_source_configs_region FOREIGN KEY (region_id) REFERENCES dashboard_management_regions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='看板管理数据来源配置'
