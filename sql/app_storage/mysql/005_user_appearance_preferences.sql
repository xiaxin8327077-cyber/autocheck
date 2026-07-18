SET @appearance_preference_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE()
      AND table_name = 'user_interface_preferences'
      AND column_name = 'theme_gradient_enabled'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD COLUMN `theme_gradient_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT ''是否启用主题渐变：1 启用，0 关闭'' AFTER `radius_px`'
);
PREPARE appearance_preference_statement FROM @appearance_preference_ddl;
EXECUTE appearance_preference_statement;
DEALLOCATE PREPARE appearance_preference_statement;

SET @appearance_preference_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE()
      AND table_name = 'user_interface_preferences'
      AND column_name = 'line_chart_style'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD COLUMN `line_chart_style` VARCHAR(16) NOT NULL DEFAULT ''straight'' COMMENT ''折线图风格：straight 直线折线，smooth 平滑曲线'' AFTER `theme_gradient_enabled`'
);
PREPARE appearance_preference_statement FROM @appearance_preference_ddl;
EXECUTE appearance_preference_statement;
DEALLOCATE PREPARE appearance_preference_statement;

SET @appearance_preference_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE constraint_schema = DATABASE()
      AND table_name = 'user_interface_preferences'
      AND constraint_name = 'chk_user_interface_theme_gradient_enabled'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD CONSTRAINT `chk_user_interface_theme_gradient_enabled` CHECK (`theme_gradient_enabled` IN (0, 1))'
);
PREPARE appearance_preference_statement FROM @appearance_preference_ddl;
EXECUTE appearance_preference_statement;
DEALLOCATE PREPARE appearance_preference_statement;

SET @appearance_preference_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE constraint_schema = DATABASE()
      AND table_name = 'user_interface_preferences'
      AND constraint_name = 'chk_user_interface_line_chart_style'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD CONSTRAINT `chk_user_interface_line_chart_style` CHECK (`line_chart_style` IN (''straight'', ''smooth''))'
);
PREPARE appearance_preference_statement FROM @appearance_preference_ddl;
EXECUTE appearance_preference_statement;
DEALLOCATE PREPARE appearance_preference_statement;
