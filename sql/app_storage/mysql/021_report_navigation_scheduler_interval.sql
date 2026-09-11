UPDATE `report_nav_scheduler_state`
SET `interval_minutes` = 30,
    `updated_at` = CURRENT_TIMESTAMP(6)
WHERE `id` = 1;
