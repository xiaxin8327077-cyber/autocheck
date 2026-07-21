CREATE TABLE IF NOT EXISTS `report_nav_card_manual_history` (
  `stat_period` VARCHAR(16) NOT NULL COMMENT '统计周期类型',
  `period_key` VARCHAR(16) NOT NULL COMMENT '真实自然周期标识',
  `card_code` VARCHAR(64) NOT NULL COMMENT '统计卡编码',
  `completed_count` INT NOT NULL DEFAULT 0 COMMENT '已完成数量',
  `incomplete_count` INT NOT NULL DEFAULT 0 COMMENT '未完成数量',
  `operator_id` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '操作人用户ID',
  `operator_username` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作人账号',
  `operator_name` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '操作人姓名',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`stat_period`, `period_key`, `card_code`),
  KEY `idx_report_nav_card_manual_history_card` (`card_code`, `stat_period`, `period_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报送导航治理统计卡自然周期历史值';

INSERT INTO `report_nav_card_manual_history` (
  `stat_period`, `period_key`, `card_code`, `completed_count`, `incomplete_count`,
  `operator_id`, `operator_username`, `operator_name`, `updated_at`
)
SELECT
  `stat_period`,
  CASE `stat_period`
    WHEN 'week' THEN CONCAT(DATE_FORMAT(CURDATE(), '%x'), '-W', DATE_FORMAT(CURDATE(), '%v'))
    WHEN 'month' THEN DATE_FORMAT(CURDATE(), '%Y-%m')
    WHEN 'quarter' THEN CONCAT(YEAR(CURDATE()), '-Q', QUARTER(CURDATE()))
    WHEN 'year' THEN CAST(YEAR(CURDATE()) AS CHAR)
  END,
  `card_code`, `completed_count`, `incomplete_count`,
  `operator_id`, `operator_username`, `operator_name`, `updated_at`
FROM `report_nav_card_manual_values`
WHERE `card_code` IN ('data_governance', 'special_governance')
ON DUPLICATE KEY UPDATE
  `completed_count`=VALUES(`completed_count`),
  `incomplete_count`=VALUES(`incomplete_count`),
  `operator_id`=VALUES(`operator_id`),
  `operator_username`=VALUES(`operator_username`),
  `operator_name`=VALUES(`operator_name`),
  `updated_at`=VALUES(`updated_at`);
