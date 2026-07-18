SET @appearance_preference_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.COLUMNS
    WHERE table_schema = DATABASE()
      AND table_name = 'user_interface_preferences'
      AND column_name = 'line_chart_style'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD COLUMN `line_chart_style` VARCHAR(16) NOT NULL DEFAULT ''straight'' COMMENT ''折线图风格：straight 直线折线，smooth 平滑曲线'' AFTER `radius_px`'
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
      AND column_name = 'vitality_theme_color'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD COLUMN `vitality_theme_color` CHAR(7) NULL COMMENT ''预留个人活力主题色，格式 #RRGGBB'' AFTER `line_chart_style`'
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
      AND column_name = 'calm_theme_color'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD COLUMN `calm_theme_color` CHAR(7) NULL COMMENT ''预留个人沉稳主题色，格式 #RRGGBB'' AFTER `vitality_theme_color`'
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

SET @appearance_preference_ddl = IF(
  EXISTS (
    SELECT 1
    FROM information_schema.TABLE_CONSTRAINTS
    WHERE constraint_schema = DATABASE()
      AND table_name = 'user_interface_preferences'
      AND constraint_name = 'chk_user_interface_vitality_theme_color'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD CONSTRAINT `chk_user_interface_vitality_theme_color` CHECK (`vitality_theme_color` IS NULL OR BINARY `vitality_theme_color` REGEXP ''^#[0-9A-F]{6}$'')'
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
      AND constraint_name = 'chk_user_interface_calm_theme_color'
  ),
  'SELECT 1',
  'ALTER TABLE `user_interface_preferences` ADD CONSTRAINT `chk_user_interface_calm_theme_color` CHECK (`calm_theme_color` IS NULL OR BINARY `calm_theme_color` REGEXP ''^#[0-9A-F]{6}$'')'
);
PREPARE appearance_preference_statement FROM @appearance_preference_ddl;
EXECUTE appearance_preference_statement;
DEALLOCATE PREPARE appearance_preference_statement;
