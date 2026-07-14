-- Auto Check MySQL application storage schema
-- Run this against an existing, manually created auto_check database before starting the application.
-- Safety: the script contains only session setup and table definitions; it never creates, drops, truncates, or populates production data.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

CREATE TABLE `app_schema_version` (
  `version` INT NOT NULL COMMENT '结构版本',
  `applied_at` DATETIME(6) NOT NULL COMMENT '应用时间',
  `source_sha256` CHAR(64) NOT NULL COMMENT '源 SQLite 文件 SHA-256',
  `description` VARCHAR(255) NOT NULL COMMENT '版本说明',
  PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='应用数据库结构版本表：记录当前 MySQL 应用存储结构版本和人工导入来源。';

CREATE TABLE `data_sources` (
  `id` VARCHAR(64) NOT NULL COMMENT '数据源 ID',
  `name` VARCHAR(191) NOT NULL COMMENT '数据源名称',
  `db_type` VARCHAR(32) NOT NULL COMMENT '数据库类型',
  `host` VARCHAR(255) NOT NULL COMMENT '主机地址',
  `port` INT NOT NULL COMMENT '端口',
  `database_name` VARCHAR(191) NOT NULL COMMENT '数据库名',
  `schema_name` VARCHAR(191) NOT NULL COMMENT 'Schema',
  `username` VARCHAR(191) NOT NULL COMMENT '用户名',
  `password_encrypted` TEXT NOT NULL COMMENT '加密密码',
  `is_default` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否默认',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据源配置表?保存 DWS、报表库等本地数据源连接配置和默认标记。';

CREATE TABLE `app_settings` (
  `key` VARCHAR(191) NOT NULL COMMENT '设置键',
  `value_json` JSON NOT NULL COMMENT '设置内容',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='应用设置表?保存系统设置、默认设置、人行逐笔校验设置、流程工具设置等结构化配置。';

CREATE TABLE `users` (
  `id` VARCHAR(64) NOT NULL COMMENT '用户 ID',
  `username` VARCHAR(191) NOT NULL COMMENT '登录账号',
  `display_name` VARCHAR(191) NOT NULL COMMENT '展示名',
  `role` VARCHAR(32) NOT NULL COMMENT '角色',
  `password_hash` TEXT NOT NULL COMMENT '密码哈希',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  `last_login_at` DATETIME(6) NULL COMMENT '最近登录时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_users_username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户账号表?保存用户、角色、状态、密码哈希和登录时间。';

CREATE TABLE `config_snapshots` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '快照 ID',
  `fingerprint` CHAR(64) NOT NULL COMMENT '配置指纹',
  `payload_json` JSON NOT NULL COMMENT '配置快照',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='配置兼容快照表?保存完整配置 payload 快照，便于兼容旧结构和后续排查。';

CREATE TABLE `run_headers` (
  `id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `kind` VARCHAR(32) NOT NULL COMMENT '历史类型',
  `run_date` DATE NULL COMMENT '业务日期',
  `run_at` DATETIME(6) NULL COMMENT '开始时间',
  `finished_at` DATETIME(6) NULL COMMENT '完成时间',
  `status` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '状态',
  `executor_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '执行人 ID',
  `executor_username` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '执行账号',
  `executor_name` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '执行人',
  `config_fingerprint` CHAR(64) NOT NULL DEFAULT '' COMMENT '配置指纹',
  `payload_json` JSON NOT NULL COMMENT '完整快照',
  PRIMARY KEY (`id`),
  KEY `idx_run_headers_sort` (`kind`, `run_date`, `run_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='历史运行头表?保存各类历史运行的公共字段和完整 payload 快照。';

CREATE TABLE `reconcile_runs` (
  `id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `config_name` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '配置名称',
  `dws_source_name` VARCHAR(191) NOT NULL DEFAULT '' COMMENT 'DWS 数据源',
  `rule_version` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '规则版本',
  `baseline_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '基准运行 ID',
  `baseline_run_at` DATETIME(6) NULL COMMENT '基准运行时间',
  `baseline_count` BIGINT NULL COMMENT '基准条数',
  `total_count` BIGINT NOT NULL DEFAULT 0 COMMENT '差异总数',
  `added_count` BIGINT NULL COMMENT '新增差异数',
  `removed_count` BIGINT NULL COMMENT '减少差异数',
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_reconcile_runs_header` FOREIGN KEY (`id`) REFERENCES `run_headers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动对数运行表?保存自动对数运行摘要、配置名称、规则版本和增量数量。';

CREATE TABLE `reconcile_run_counts` (
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `count_type` VARCHAR(64) NOT NULL COMMENT '统计类型',
  `label` VARCHAR(191) NOT NULL COMMENT '统计标签',
  `count_value` BIGINT NOT NULL COMMENT '统计值',
  PRIMARY KEY (`run_id`, `count_type`, `label`),
  CONSTRAINT `fk_reconcile_counts_run` FOREIGN KEY (`run_id`) REFERENCES `reconcile_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动对数运行统计表?保存匹配状态、差异类型等聚合统计。';

CREATE TABLE `reconcile_results` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '结果 ID',
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `result_order` BIGINT NOT NULL COMMENT '结果顺序',
  `project_code` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '项目编号',
  `project_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '项目名称',
  `asset_total` DECIMAL(38,12) NULL COMMENT '资产合计',
  `liability_equity_total` DECIMAL(38,12) NULL COMMENT '负债及权益合计',
  `received_trust_balance` DECIMAL(38,12) NULL COMMENT '实收信托余额',
  `difference` DECIMAL(38,12) NULL COMMENT '差异金额',
  `direction` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '差异方向',
  `difference_reason` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '差异类型',
  `match_status` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '匹配状态',
  `valuation_asset_total` DECIMAL(38,12) NULL COMMENT '估值表资产合计',
  `payload_json` JSON NOT NULL COMMENT '结果快照',
  PRIMARY KEY (`id`),
  KEY `idx_reconcile_results_run` (`run_id`, `result_order`),
  KEY `idx_reconcile_results_project` (`project_code`),
  KEY `idx_reconcile_results_reason` (`difference_reason`, `match_status`),
  CONSTRAINT `fk_reconcile_results_run` FOREIGN KEY (`run_id`) REFERENCES `reconcile_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动对数结果明细表?保存项目编号、差异类型、匹配状态、差异金额等结果热字段。';

CREATE TABLE `reconcile_result_details` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '详情 ID',
  `result_id` BIGINT NOT NULL COMMENT '结果 ID',
  `detail_order` BIGINT NOT NULL COMMENT '详情顺序',
  `kind` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '详情类型',
  `specific_reason` TEXT NOT NULL COMMENT '具体原因',
  `data_json` JSON NOT NULL COMMENT '详情数据',
  PRIMARY KEY (`id`),
  KEY `idx_reconcile_result_details_result` (`result_id`, `detail_order`),
  CONSTRAINT `fk_reconcile_details_result` FOREIGN KEY (`result_id`) REFERENCES `reconcile_results` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动对数结果详情表?保存结构化详情类型、具体原因和详情 payload。';

CREATE TABLE `reconcile_delta_results` (
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `delta_type` VARCHAR(32) NOT NULL COMMENT '增量类型',
  `result_order` BIGINT NOT NULL COMMENT '结果顺序',
  `payload_json` JSON NOT NULL COMMENT '增量快照',
  PRIMARY KEY (`run_id`, `delta_type`, `result_order`),
  CONSTRAINT `fk_reconcile_delta_run` FOREIGN KEY (`run_id`) REFERENCES `reconcile_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='自动对数增量差异表?保存本次新增差异和减少差异快照。';

CREATE TABLE `db_validation_runs` (
  `id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `report_date` DATE NULL COMMENT '报告期',
  `result_count` BIGINT NOT NULL DEFAULT 0 COMMENT '结果数',
  `warning_count` BIGINT NOT NULL DEFAULT 0 COMMENT '告警数',
  `table_count` BIGINT NOT NULL DEFAULT 0 COMMENT '选表数量',
  `enable_public_info_check` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '公开信息校验',
  `enable_template_check` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '模板校验',
  `excel_filename` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '结果文件名',
  `excel_path` VARCHAR(2048) NOT NULL DEFAULT '' COMMENT '结果文件路径',
  `download_url` VARCHAR(2048) NOT NULL DEFAULT '' COMMENT '下载地址',
  PRIMARY KEY (`id`),
  KEY `idx_db_validation_runs_sort` (`report_date`),
  CONSTRAINT `fk_db_validation_runs_header` FOREIGN KEY (`id`) REFERENCES `run_headers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人行逐笔校验运行表?保存逐笔校验报告期、结果数、告警数、校验开关和下载路径。';

CREATE TABLE `db_validation_selected_tables` (
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `table_order` BIGINT NOT NULL COMMENT '选表顺序',
  `table_code` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'ZG 表编号',
  PRIMARY KEY (`run_id`, `table_order`),
  CONSTRAINT `fk_db_validation_selected_run` FOREIGN KEY (`run_id`) REFERENCES `db_validation_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人行逐笔校验选表明细表?保存一次逐笔校验运行中勾选的 ZG 表清单。';

CREATE TABLE `db_validation_warnings` (
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `warning_order` BIGINT NOT NULL COMMENT '告警顺序',
  `message` TEXT NOT NULL COMMENT '告警内容',
  PRIMARY KEY (`run_id`, `warning_order`),
  CONSTRAINT `fk_db_validation_warnings_run` FOREIGN KEY (`run_id`) REFERENCES `db_validation_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人行逐笔校验告警表?保存一次逐笔校验运行产生的告警信息。';

CREATE TABLE `db_validation_result_rows` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '结果行 ID',
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `row_order` BIGINT NOT NULL COMMENT '行顺序',
  `table_code` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'ZG 表编号',
  `rule_id` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '规则编号',
  `severity` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '级别',
  `message` TEXT NOT NULL COMMENT '消息',
  `detail` TEXT NOT NULL COMMENT '详情',
  `payload_json` JSON NOT NULL COMMENT '行快照',
  PRIMARY KEY (`id`),
  KEY `idx_db_validation_result_rows_run` (`run_id`, `row_order`),
  CONSTRAINT `fk_db_validation_results_run` FOREIGN KEY (`run_id`) REFERENCES `db_validation_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='人行逐笔校验结果行表?保存逐笔校验结果行的表号、规则、级别、消息和完整行快照。';

CREATE TABLE `flow_chain_runs` (
  `id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `chain_id` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '链路编号',
  `chain_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '链路名称',
  `is_multi_chain` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否多链路',
  `trigger_type` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '触发方式',
  `executor_name` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '执行人',
  `status` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '状态',
  `error` TEXT NOT NULL COMMENT '错误信息',
  `step_count` BIGINT NOT NULL DEFAULT 0 COMMENT '步骤数',
  `duration_seconds` BIGINT NOT NULL DEFAULT 0 COMMENT '耗时秒数',
  PRIMARY KEY (`id`),
  CONSTRAINT `fk_flow_runs_header` FOREIGN KEY (`id`) REFERENCES `run_headers` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='流程链执行运行表?保存流程链名称、触发方式、执行人、状态、错误、步骤数和总耗时。';

CREATE TABLE `flow_chain_run_steps` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '步骤 ID',
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `step_order` BIGINT NOT NULL COMMENT '步骤顺序',
  `flow_id` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '流程编号',
  `name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '步骤名称',
  `status` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '状态',
  `sp_task_id` VARCHAR(191) NOT NULL DEFAULT '' COMMENT '申报平台任务号',
  `start_time` DATETIME(6) NULL COMMENT '开始时间',
  `end_time` DATETIME(6) NULL COMMENT '结束时间',
  `duration_seconds` BIGINT NULL COMMENT '耗时秒数',
  `payload_json` JSON NOT NULL COMMENT '步骤快照',
  PRIMARY KEY (`id`),
  KEY `idx_flow_chain_run_steps_run` (`run_id`, `step_order`),
  CONSTRAINT `fk_flow_steps_run` FOREIGN KEY (`run_id`) REFERENCES `flow_chain_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='流程链执行步骤表?保存每个流程步骤的流程编号、名称、状态、任务号和起止时间。';

CREATE TABLE `flow_chain_run_logs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '日志 ID',
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `log_order` BIGINT NOT NULL COMMENT '日志顺序',
  `log_time` TIME(6) NULL COMMENT '日志时间',
  `message` TEXT NOT NULL COMMENT '日志内容',
  `progress` BIGINT NULL COMMENT '进度',
  `step` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '当前步骤',
  `payload_json` JSON NOT NULL COMMENT '日志快照',
  PRIMARY KEY (`id`),
  KEY `idx_flow_chain_run_logs_run` (`run_id`, `log_order`),
  CONSTRAINT `fk_flow_logs_run` FOREIGN KEY (`run_id`) REFERENCES `flow_chain_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='流程链执行日志表?保存流程链执行过程中的日志、进度和当前步骤。';

CREATE TABLE `flow_chain_run_details` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '链路明细 ID',
  `run_id` VARCHAR(64) NOT NULL COMMENT '运行 ID',
  `chain_order` BIGINT NOT NULL COMMENT '链路顺序',
  `chain_name` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '链路名称',
  `status` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '状态',
  `step_count` BIGINT NOT NULL DEFAULT 0 COMMENT '步骤数',
  `duration_seconds` BIGINT NOT NULL DEFAULT 0 COMMENT '耗时秒数',
  `error` TEXT NOT NULL COMMENT '错误信息',
  `payload_json` JSON NOT NULL COMMENT '链路快照',
  PRIMARY KEY (`id`),
  KEY `idx_flow_chain_run_details_run` (`run_id`, `chain_order`),
  CONSTRAINT `fk_flow_details_run` FOREIGN KEY (`run_id`) REFERENCES `flow_chain_runs` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='流程链执行链路明细表?保存单链路或多链路合并历史中的链路详情。';

CREATE TABLE `storage_migration_runs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '迁移 ID',
  `source_type` VARCHAR(64) NOT NULL COMMENT '来源类型',
  `source_path` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '来源路径',
  `source_key` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '来源子类',
  `source_fingerprint` CHAR(64) NOT NULL DEFAULT '' COMMENT '来源指纹',
  `migrated_count` BIGINT NOT NULL DEFAULT 0 COMMENT '迁移条数',
  `skipped_count` BIGINT NOT NULL DEFAULT 0 COMMENT '跳过条数',
  `status` VARCHAR(32) NOT NULL COMMENT '状态',
  `message` TEXT NOT NULL COMMENT '消息',
  `started_at` DATETIME(6) NOT NULL COMMENT '开始时间',
  `finished_at` DATETIME(6) NULL COMMENT '完成时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_storage_migration_source` (`source_type`, `source_path`, `source_key`, `source_fingerprint`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据迁移记录表?记录旧 SQLite/旧 JSON 来源的迁移路径、指纹、条数和状态。';
