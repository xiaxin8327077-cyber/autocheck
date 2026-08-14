CREATE TABLE IF NOT EXISTS db_validation_mapping_snapshots (
    id BIGINT NOT NULL AUTO_INCREMENT,
    signature_json TEXT NOT NULL,
    refresh_source VARCHAR(32) NOT NULL,
    status VARCHAR(20) NOT NULL,
    table_count INT NOT NULL DEFAULT 0,
    field_count INT NOT NULL DEFAULT 0,
    unmapped_field_count INT NOT NULL DEFAULT 0,
    required_missing_count INT NOT NULL DEFAULT 0,
    missing_physical_count INT NOT NULL DEFAULT 0,
    error_message VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_db_validation_mapping_snapshots_status (status, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS db_validation_mapping_tables (
    id BIGINT NOT NULL AUTO_INCREMENT,
    snapshot_id BIGINT NULL,
    relation_type VARCHAR(20) NOT NULL,
    logical_code VARCHAR(64) NOT NULL,
    scope_code VARCHAR(32) NOT NULL DEFAULT '',
    automatic_table_name VARCHAR(128) NOT NULL,
    override_table_name VARCHAR(128) NULL,
    effective_table_name VARCHAR(128) NOT NULL,
    mapping_status VARCHAR(32) NOT NULL DEFAULT 'mapped',
    status_message VARCHAR(500) NULL,
    is_seed TINYINT(1) NOT NULL DEFAULT 0,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_db_validation_mapping_tables_relation (relation_type, logical_code, scope_code),
    KEY idx_db_validation_mapping_tables_snapshot (snapshot_id),
    CONSTRAINT fk_db_validation_mapping_tables_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES db_validation_mapping_snapshots (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS db_validation_mapping_fields (
    id BIGINT NOT NULL AUTO_INCREMENT,
    snapshot_id BIGINT NOT NULL,
    table_mapping_id BIGINT NOT NULL,
    chinese_name VARCHAR(255) NULL,
    automatic_field_name VARCHAR(128) NULL,
    override_field_name VARCHAR(128) NULL,
    effective_field_name VARCHAR(128) NULL,
    mapping_status VARCHAR(32) NOT NULL,
    is_required TINYINT(1) NOT NULL DEFAULT 0,
    status_message VARCHAR(500) NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_db_validation_mapping_fields_logical (snapshot_id, table_mapping_id, chinese_name),
    KEY idx_db_validation_mapping_fields_status (snapshot_id, mapping_status),
    CONSTRAINT fk_db_validation_mapping_fields_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES db_validation_mapping_snapshots (id) ON DELETE CASCADE,
    CONSTRAINT fk_db_validation_mapping_fields_table FOREIGN KEY (table_mapping_id)
        REFERENCES db_validation_mapping_tables (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS db_validation_cross_table_mappings (
    id BIGINT NOT NULL AUTO_INCREMENT,
    mapping_code VARCHAR(128) NOT NULL,
    logical_code VARCHAR(64) NOT NULL,
    scope_code VARCHAR(32) NOT NULL DEFAULT '',
    automatic_detail_field_name VARCHAR(128) NOT NULL,
    override_detail_field_name VARCHAR(128) NULL,
    effective_detail_field_name VARCHAR(128) NOT NULL,
    automatic_template_table_name VARCHAR(128) NOT NULL,
    override_template_table_name VARCHAR(128) NULL,
    effective_template_table_name VARCHAR(128) NOT NULL,
    automatic_template_field_name VARCHAR(128) NOT NULL,
    override_template_field_name VARCHAR(128) NULL,
    effective_template_field_name VARCHAR(128) NOT NULL,
    mapping_status VARCHAR(32) NOT NULL DEFAULT 'mapped',
    status_message VARCHAR(500) NULL,
    is_seed TINYINT(1) NOT NULL DEFAULT 0,
    refreshed_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_db_validation_cross_table_mapping_code (mapping_code),
    KEY idx_db_validation_cross_table_scope (logical_code, scope_code, mapping_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS db_validation_mapping_overrides (
    id BIGINT NOT NULL AUTO_INCREMENT,
    mapping_kind VARCHAR(20) NOT NULL,
    relation_type VARCHAR(20) NOT NULL,
    logical_code VARCHAR(64) NOT NULL,
    scope_code VARCHAR(32) NOT NULL DEFAULT '',
    chinese_name VARCHAR(255) NOT NULL DEFAULT '',
    override_value VARCHAR(500) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_by VARCHAR(64) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_by VARCHAR(64) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_db_validation_mapping_overrides_target
        (mapping_kind, relation_type, logical_code, scope_code, chinese_name),
    KEY idx_db_validation_mapping_overrides_active (active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS db_validation_mapping_audit_logs (
    id BIGINT NOT NULL AUTO_INCREMENT,
    override_id BIGINT NULL,
    action_code VARCHAR(20) NOT NULL,
    mapping_kind VARCHAR(20) NOT NULL,
    relation_type VARCHAR(20) NOT NULL,
    logical_code VARCHAR(64) NOT NULL,
    scope_code VARCHAR(32) NOT NULL DEFAULT '',
    chinese_name VARCHAR(255) NOT NULL DEFAULT '',
    value_before VARCHAR(500) NULL,
    value_after VARCHAR(500) NULL,
    reason VARCHAR(500) NOT NULL,
    operator_user_id VARCHAR(64) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_db_validation_mapping_audit_target
        (mapping_kind, relation_type, logical_code, scope_code, chinese_name),
    CONSTRAINT fk_db_validation_mapping_audit_override FOREIGN KEY (override_id)
        REFERENCES db_validation_mapping_overrides (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO db_validation_mapping_tables
    (snapshot_id, relation_type, logical_code, scope_code, automatic_table_name,
     override_table_name, effective_table_name, mapping_status, status_message, is_seed, updated_at)
VALUES
    (NULL, 'detail', 'ZG01', '', 'zgxgzh_baseinfo_zg01_26', NULL, 'zgxgzh_baseinfo_zg01_26', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG02', '', 'zgxgzh_begraiseinfo_zg02_26', NULL, 'zgxgzh_begraiseinfo_zg02_26', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG03', '', 'zgxgzh_projendinfo_zg03_26', NULL, 'zgxgzh_projendinfo_zg03_26', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG04', '', 'zgxgzh_projholdinfo_zg04', NULL, 'zgxgzh_projholdinfo_zg04', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG05', '', 'zgxgzh_projdebt_zg05_2024', NULL, 'zgxgzh_projdebt_zg05_2024', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG06', '', 'zgxgzh_beneficial_zg06', NULL, 'zgxgzh_beneficial_zg06', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG07', '', 'zgxgzh_ioudetail_zg07', NULL, 'zgxgzh_ioudetail_zg07', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG08', '', 'zgxgzh_spvdetail_zg08', NULL, 'zgxgzh_spvdetail_zg08', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG09', '', 'zgxgzh_debtordate_zg09', NULL, 'zgxgzh_debtordate_zg09', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG10', '', 'zgxgzh_surecinfo_zg10', NULL, 'zgxgzh_surecinfo_zg10', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG11', '', 'zgxgzh_industinfo_zg11', NULL, 'zgxgzh_industinfo_zg11', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG12', '', 'zgzgzh_zg12', NULL, 'zgzgzh_zg12', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'detail', 'ZG13', '', 'zgzgzh_zg13', NULL, 'zgzgzh_zg13', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'template', 'ZG09', '1', 'balance_sheet_info', NULL, 'balance_sheet_info', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'template', 'ZG09', '2', 'balance_sheet_info_zcglxt', NULL, 'balance_sheet_info_zcglxt', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'template', 'ZG10', '1', 'balance_sheet_info2', NULL, 'balance_sheet_info2', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'template', 'ZG10', '2', 'balance_sheet_info2_zcglxt', NULL, 'balance_sheet_info2_zcglxt', 'mapped', NULL, 1, NOW(6)),
    (NULL, 'public_info', 'PUBLIC_INFO', '', 'public_information_rh', NULL, 'public_information_rh', 'mapped', NULL, 1, NOW(6))
ON DUPLICATE KEY UPDATE
    automatic_table_name = VALUES(automatic_table_name),
    effective_table_name = COALESCE(override_table_name, VALUES(automatic_table_name)),
    is_seed = 1,
    updated_at = VALUES(updated_at);

INSERT INTO db_validation_cross_table_mappings
    (mapping_code, logical_code, scope_code,
     automatic_detail_field_name, override_detail_field_name, effective_detail_field_name,
     automatic_template_table_name, override_template_table_name, effective_template_table_name,
     automatic_template_field_name, override_template_field_name, effective_template_field_name,
     mapping_status, status_message, is_seed, refreshed_at, updated_at)
VALUES
    ('ZG09:1:fb00001', 'ZG09', '1', 'fb00001', NULL, 'fb00001',
     'balance_sheet_info', NULL, 'balance_sheet_info', 'f1', NULL, 'f1',
     'mapped', NULL, 1, NOW(6), NOW(6)),
    ('ZG09:1:fb00002', 'ZG09', '1', 'fb00002', NULL, 'fb00002',
     'balance_sheet_info', NULL, 'balance_sheet_info', 'f2', NULL, 'f2',
     'mapped', NULL, 1, NOW(6), NOW(6)),
    ('ZG09:2:fb00001', 'ZG09', '2', 'fb00001', NULL, 'fb00001',
     'balance_sheet_info_zcglxt', NULL, 'balance_sheet_info_zcglxt', 'f1', NULL, 'f1',
     'mapped', NULL, 1, NOW(6), NOW(6)),
    ('ZG09:2:fb00002', 'ZG09', '2', 'fb00002', NULL, 'fb00002',
     'balance_sheet_info_zcglxt', NULL, 'balance_sheet_info_zcglxt', 'f2', NULL, 'f2',
     'mapped', NULL, 1, NOW(6), NOW(6))
ON DUPLICATE KEY UPDATE
    automatic_detail_field_name = VALUES(automatic_detail_field_name),
    effective_detail_field_name = COALESCE(override_detail_field_name, VALUES(automatic_detail_field_name)),
    automatic_template_table_name = VALUES(automatic_template_table_name),
    effective_template_table_name = COALESCE(override_template_table_name, VALUES(automatic_template_table_name)),
    automatic_template_field_name = VALUES(automatic_template_field_name),
    effective_template_field_name = COALESCE(override_template_field_name, VALUES(automatic_template_field_name)),
    is_seed = 1,
    refreshed_at = VALUES(refreshed_at),
    updated_at = VALUES(updated_at);
