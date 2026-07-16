CREATE TABLE IF NOT EXISTS `report_nav_processes` (
  `process_code` VARCHAR(64) NOT NULL,
  `process_name` VARCHAR(128) NOT NULL,
  `display_order` INT NOT NULL,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `allow_manual_step_completion` TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`process_code`),
  KEY `idx_report_nav_processes_order` (`enabled`, `display_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_process_months` (
  `process_code` VARCHAR(64) NOT NULL,
  `month_no` TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (`process_code`, `month_no`),
  CONSTRAINT `fk_report_nav_process_months_process`
    FOREIGN KEY (`process_code`) REFERENCES `report_nav_processes` (`process_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_steps` (
  `step_code` VARCHAR(64) NOT NULL,
  `process_code` VARCHAR(64) NOT NULL,
  `step_name` VARCHAR(255) NOT NULL,
  `display_order` INT NOT NULL,
  `evaluator_key` VARCHAR(64) NOT NULL,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `default_completed` TINYINT(1) NOT NULL DEFAULT 0,
  `manual_completion_allowed` TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`step_code`),
  KEY `idx_report_nav_steps_process_order` (`process_code`, `enabled`, `display_order`),
  CONSTRAINT `fk_report_nav_steps_process`
    FOREIGN KEY (`process_code`) REFERENCES `report_nav_processes` (`process_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_step_dependencies` (
  `step_code` VARCHAR(64) NOT NULL,
  `depends_on_step_code` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`step_code`, `depends_on_step_code`),
  CONSTRAINT `fk_report_nav_dependencies_step`
    FOREIGN KEY (`step_code`) REFERENCES `report_nav_steps` (`step_code`),
  CONSTRAINT `fk_report_nav_dependencies_target`
    FOREIGN KEY (`depends_on_step_code`) REFERENCES `report_nav_steps` (`step_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_step_sources` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `step_code` VARCHAR(64) NOT NULL,
  `source_role` VARCHAR(64) NOT NULL,
  `data_source_name` VARCHAR(128) NOT NULL,
  `table_name` VARCHAR(255) NOT NULL,
  `display_order` INT NOT NULL,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_nav_step_sources_role` (`step_code`, `source_role`, `display_order`),
  CONSTRAINT `fk_report_nav_step_sources_step`
    FOREIGN KEY (`step_code`) REFERENCES `report_nav_steps` (`step_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_step_fields` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `step_source_id` BIGINT NOT NULL,
  `field_role` VARCHAR(64) NOT NULL,
  `column_name` VARCHAR(128) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_nav_step_fields_role` (`step_source_id`, `field_role`),
  CONSTRAINT `fk_report_nav_step_fields_source`
    FOREIGN KEY (`step_source_id`) REFERENCES `report_nav_step_sources` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_step_values` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `step_code` VARCHAR(64) NOT NULL,
  `value_role` VARCHAR(64) NOT NULL,
  `value_text` VARCHAR(255) NOT NULL,
  `value_type` VARCHAR(32) NOT NULL DEFAULT 'text',
  `display_order` INT NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_report_nav_step_values_role` (`step_code`, `value_role`, `display_order`),
  CONSTRAINT `fk_report_nav_step_values_step`
    FOREIGN KEY (`step_code`) REFERENCES `report_nav_steps` (`step_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_step_overrides` (
  `report_month` CHAR(7) NOT NULL,
  `step_code` VARCHAR(64) NOT NULL,
  `completed` TINYINT(1) NOT NULL DEFAULT 1,
  `operator_id` VARCHAR(64) NOT NULL DEFAULT '',
  `operator_username` VARCHAR(128) NOT NULL DEFAULT '',
  `operator_name` VARCHAR(128) NOT NULL DEFAULT '',
  `created_at` DATETIME(6) NOT NULL,
  `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`report_month`, `step_code`),
  CONSTRAINT `fk_report_nav_step_overrides_step`
    FOREIGN KEY (`step_code`) REFERENCES `report_nav_steps` (`step_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_step_snapshots` (
  `report_month` CHAR(7) NOT NULL,
  `step_code` VARCHAR(64) NOT NULL,
  `auto_status` VARCHAR(32) NOT NULL,
  `effective_status` VARCHAR(32) NOT NULL,
  `completion_source` VARCHAR(32) NOT NULL,
  `status_message` VARCHAR(255) NOT NULL DEFAULT '',
  `error_message` TEXT NULL,
  `auto_completed_at` DATETIME(6) NULL,
  `evaluated_at` DATETIME(6) NOT NULL,
  `run_id` BIGINT NULL,
  PRIMARY KEY (`report_month`, `step_code`),
  KEY `idx_report_nav_step_snapshots_run` (`run_id`),
  CONSTRAINT `fk_report_nav_step_snapshots_step`
    FOREIGN KEY (`step_code`) REFERENCES `report_nav_steps` (`step_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_process_snapshots` (
  `report_month` CHAR(7) NOT NULL,
  `process_code` VARCHAR(64) NOT NULL,
  `total_steps` INT NOT NULL,
  `completed_steps` INT NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `completed_at` DATETIME(6) NULL,
  `evaluated_at` DATETIME(6) NOT NULL,
  `run_id` BIGINT NULL,
  PRIMARY KEY (`report_month`, `process_code`),
  KEY `idx_report_nav_process_snapshots_run` (`run_id`),
  CONSTRAINT `fk_report_nav_process_snapshots_process`
    FOREIGN KEY (`process_code`) REFERENCES `report_nav_processes` (`process_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_card_snapshots` (
  `stat_period` VARCHAR(16) NOT NULL,
  `card_code` VARCHAR(64) NOT NULL,
  `total_count` INT NOT NULL,
  `completed_count` INT NOT NULL,
  `incomplete_count` INT NOT NULL,
  `completion_rate` DECIMAL(7,4) NOT NULL DEFAULT 0,
  `evaluated_at` DATETIME(6) NOT NULL,
  `run_id` BIGINT NULL,
  PRIMARY KEY (`stat_period`, `card_code`),
  KEY `idx_report_nav_card_snapshots_run` (`run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_monthly_schedules` (
  `report_month` CHAR(7) NOT NULL,
  `process_code` VARCHAR(64) NOT NULL,
  `report_date` DATE NOT NULL,
  `source_type` VARCHAR(32) NOT NULL,
  `source_year` SMALLINT NULL,
  `updated_by` VARCHAR(128) NOT NULL DEFAULT '',
  `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`report_month`, `process_code`),
  CONSTRAINT `fk_report_nav_monthly_schedules_process`
    FOREIGN KEY (`process_code`) REFERENCES `report_nav_processes` (`process_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_stat_runs` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `trigger_type` VARCHAR(32) NOT NULL,
  `report_month` CHAR(7) NOT NULL,
  `business_report_date` DATE NULL,
  `started_at` DATETIME(6) NOT NULL,
  `finished_at` DATETIME(6) NULL,
  `status` VARCHAR(32) NOT NULL,
  `completed_processes` INT NOT NULL DEFAULT 0,
  `failed_steps` INT NOT NULL DEFAULT 0,
  `error_message` TEXT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_report_nav_stat_runs_month_started` (`report_month`, `started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `report_nav_scheduler_state` (
  `id` TINYINT NOT NULL,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `interval_minutes` INT NOT NULL DEFAULT 10,
  `next_run_at` DATETIME(6) NULL,
  `lock_owner` VARCHAR(64) NULL,
  `lock_until` DATETIME(6) NULL,
  `last_started_at` DATETIME(6) NULL,
  `last_finished_at` DATETIME(6) NULL,
  `last_status` VARCHAR(32) NULL,
  `last_error` TEXT NULL,
  `updated_at` DATETIME(6) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
