CREATE TABLE IF NOT EXISTS `report_nav_card_provider_states` (
  `card_code` VARCHAR(64) NOT NULL COMMENT '统计卡编码',
  `owner` VARCHAR(64) NOT NULL COMMENT '提供方模块编码',
  `registration_token` VARCHAR(64) NOT NULL COMMENT '当前提供方注册令牌',
  `semantics_version` INT NOT NULL COMMENT '统计口径版本',
  `provider_active` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '提供方是否处于活动状态',
  `stale` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '最近成功快照是否已过期',
  `last_attempt_at` DATETIME(6) NULL COMMENT '最近尝试采集时间',
  `last_success_at` DATETIME(6) NULL COMMENT '最近成功采集时间',
  `last_success_period_key` VARCHAR(16) NULL COMMENT '最近成功采集的月份周期标识',
  `last_error` TEXT NULL COMMENT '最近一次脱敏错误',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`card_code`),
  KEY `idx_report_nav_card_provider_states_owner` (`owner`, `provider_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航模块统计提供方持久状态';

SET @report_nav_provider_token_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE()
      AND table_name = 'report_nav_card_provider_states'
      AND column_name = 'registration_token'
  ),
  'SELECT 1',
  'ALTER TABLE `report_nav_card_provider_states` ADD COLUMN `registration_token` VARCHAR(64) NOT NULL DEFAULT '''' COMMENT ''当前提供方注册令牌'' AFTER `owner`'
);
PREPARE report_nav_provider_token_statement FROM @report_nav_provider_token_ddl;
EXECUTE report_nav_provider_token_statement;
DEALLOCATE PREPARE report_nav_provider_token_statement;

UPDATE `report_nav_card_provider_states`
SET `provider_active`=0, `stale`=1
WHERE `registration_token`='';

SET @report_nav_failed_providers_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE()
      AND table_name = 'report_nav_stat_runs'
      AND column_name = 'failed_providers'
  ),
  'SELECT 1',
  'ALTER TABLE `report_nav_stat_runs` ADD COLUMN `failed_providers` INT NOT NULL DEFAULT 0 COMMENT ''模块统计提供方异常数'' AFTER `failed_steps`'
);
PREPARE report_nav_failed_providers_statement FROM @report_nav_failed_providers_ddl;
EXECUTE report_nav_failed_providers_statement;
DEALLOCATE PREPARE report_nav_failed_providers_statement;
