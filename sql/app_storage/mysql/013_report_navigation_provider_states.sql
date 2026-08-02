CREATE TABLE IF NOT EXISTS `report_nav_card_provider_states` (
  `card_code` VARCHAR(64) NOT NULL COMMENT '统计卡编码',
  `owner` VARCHAR(64) NOT NULL COMMENT '提供方模块编码',
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
