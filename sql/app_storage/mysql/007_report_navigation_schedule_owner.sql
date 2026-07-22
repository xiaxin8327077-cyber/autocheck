-- 报送日程月度负责人字段（升级脚本 007，可重复执行）
SET @report_nav_owner_column_exists = (
  SELECT COUNT(*)
  FROM information_schema.columns
  WHERE table_schema = DATABASE()
    AND table_name = 'report_nav_monthly_schedules'
    AND column_name = 'owner_name'
);

SET @report_nav_owner_column_sql = IF(
  @report_nav_owner_column_exists = 0,
  'ALTER TABLE `report_nav_monthly_schedules` ADD COLUMN `owner_name` VARCHAR(128) NULL COMMENT ''月度负责人'' AFTER `source_year`',
  'SELECT 1'
);

PREPARE report_nav_owner_column_statement FROM @report_nav_owner_column_sql;
EXECUTE report_nav_owner_column_statement;
DEALLOCATE PREPARE report_nav_owner_column_statement;
