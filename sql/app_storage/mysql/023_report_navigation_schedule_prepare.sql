-- 独立日期预生成任务：提前提醒人工维护，月末仍缺失时继承上年同月日期。
-- 依赖 022_scheduled_tasks.sql；不覆盖已有任务的配置、启停状态及执行记录。
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

INSERT INTO `scheduled_tasks`
  (`task_code`, `task_name`, `schedule_type`, `interval_minutes`, `daily_time`, `enabled`, `created_at`, `updated_at`)
VALUES
  ('report_navigation_schedule_prepare', '报送日期预生成', 'daily', NULL, '15:00', 1, CURRENT_TIMESTAMP(6), CURRENT_TIMESTAMP(6))
ON DUPLICATE KEY UPDATE `task_code`=VALUES(`task_code`);
