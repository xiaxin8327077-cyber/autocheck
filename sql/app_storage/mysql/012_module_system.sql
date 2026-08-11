-- Auto Check module system storage schema
-- Run this against an existing, manually created auto_check database after backing up production data.
-- Safety: the script creates only idempotent platform tables and never changes app_schema_version or application data.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

CREATE TABLE IF NOT EXISTS `app_modules` (
  `module_id` VARCHAR(64) NOT NULL COMMENT '模块 ID',
  `module_version` VARCHAR(32) NOT NULL COMMENT '当前模块功能版本',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `status` VARCHAR(32) NOT NULL COMMENT '当前状态',
  `last_error` TEXT NULL COMMENT '最近启动或迁移错误摘要',
  `installed_at` DATETIME(6) NOT NULL COMMENT '首次发现时间',
  `updated_at` DATETIME(6) NOT NULL COMMENT '最近更新时间',
  PRIMARY KEY (`module_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模块注册状态表，保存内置模块的版本、启用状态和最近错误摘要。';

CREATE TABLE IF NOT EXISTS `app_module_schema_versions` (
  `module_id` VARCHAR(64) NOT NULL COMMENT '模块 ID',
  `schema_version` INT NOT NULL COMMENT '已应用结构版本',
  `applied_at` DATETIME(6) NOT NULL COMMENT '应用时间',
  `checksum` CHAR(64) NOT NULL COMMENT '迁移文件 SHA-256 摘要',
  PRIMARY KEY (`module_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模块结构版本表，独立记录各模块已应用迁移的版本与摘要。';

CREATE TABLE IF NOT EXISTS `app_module_migration_history` (
  `id` BIGINT NOT NULL AUTO_INCREMENT COMMENT '记录主键',
  `module_id` VARCHAR(64) NOT NULL COMMENT '模块 ID',
  `from_version` INT NOT NULL COMMENT '原结构版本',
  `to_version` INT NOT NULL COMMENT '目标结构版本',
  `status` VARCHAR(32) NOT NULL COMMENT '迁移状态（running、completed、failed）',
  `checksum` CHAR(64) NOT NULL COMMENT '迁移 SHA-256 摘要',
  `started_at` DATETIME(6) NOT NULL COMMENT '开始时间',
  `finished_at` DATETIME(6) NULL COMMENT '完成时间',
  `error_message` TEXT NULL COMMENT '脱敏错误摘要',
  PRIMARY KEY (`id`),
  KEY `idx_app_module_migration_history_module_started` (`module_id`, `started_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模块迁移执行历史表，保存迁移状态、时间和脱敏错误摘要。';
