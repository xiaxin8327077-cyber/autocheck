-- 统一定时任务管理：scheduled_tasks 表与内置任务预置

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

CREATE TABLE IF NOT EXISTS `scheduled_tasks` (
  `task_code` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '内置任务码，全局唯一',
  `task_name` VARCHAR(191) NOT NULL COMMENT '任务显示名',
  `schedule_type` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '调度类型：interval/daily',
  `interval_minutes` INT NULL COMMENT '间隔分钟数（schedule_type=interval 时有效，1..10080）',
  `daily_time` VARCHAR(5) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '每日执行时间 HH:MM（schedule_type=daily 时有效）',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `next_run_at` DATETIME(6) NULL COMMENT '下次计划执行时间',
  `last_started_at` DATETIME(6) NULL COMMENT '最近一次开始执行时间',
  `last_finished_at` DATETIME(6) NULL COMMENT '最近一次执行结束时间',
  `last_status` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '最近一次执行状态：success/failed',
  `last_error` TEXT NULL COMMENT '最近一次执行错误信息',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`task_code`),
  KEY `ix_scheduled_tasks_next_run` (`next_run_at`, `enabled`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='统一定时任务配置与状态表';

-- 预置内置任务：报送导航统计，每 30 分钟
INSERT INTO `scheduled_tasks`
  (`task_code`, `task_name`, `schedule_type`, `interval_minutes`, `daily_time`, `enabled`, `created_at`, `updated_at`)
VALUES
  ('report_navigation_statistics', '报送导航统计', 'interval', 30, NULL, 1, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE `task_name`=VALUES(`task_name`);

-- 预置内置任务：通知过期清理，每 6 小时（360 分钟）
INSERT INTO `scheduled_tasks`
  (`task_code`, `task_name`, `schedule_type`, `interval_minutes`, `daily_time`, `enabled`, `created_at`, `updated_at`)
VALUES
  ('notification_cleanup', '通知过期清理', 'interval', 360, NULL, 1, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE `task_name`=VALUES(`task_name`);

-- 预置内置任务：逐笔校验字段映射刷新，每天 00:00
INSERT INTO `scheduled_tasks`
  (`task_code`, `task_name`, `schedule_type`, `interval_minutes`, `daily_time`, `enabled`, `created_at`, `updated_at`)
VALUES
  ('db_validation_field_mapping_refresh', '逐笔校验字段映射刷新', 'daily', NULL, '00:00', 1, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE `task_name`=VALUES(`task_name`);
