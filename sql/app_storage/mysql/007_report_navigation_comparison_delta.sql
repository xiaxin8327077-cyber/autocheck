SET @report_navigation_comparison_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE()
      AND table_name = 'report_nav_card_snapshots'
      AND column_name = 'comparison_delta'
  ),
  'SELECT 1',
  'ALTER TABLE `report_nav_card_snapshots` ADD COLUMN `comparison_delta` INT NULL COMMENT ''与上一完整统计周期相比的已完成数变化'' AFTER `incomplete_count`'
);
PREPARE report_navigation_comparison_statement FROM @report_navigation_comparison_ddl;
EXECUTE report_navigation_comparison_statement;
DEALLOCATE PREPARE report_navigation_comparison_statement;
