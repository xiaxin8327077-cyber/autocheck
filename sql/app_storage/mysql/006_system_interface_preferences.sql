CREATE TABLE IF NOT EXISTS `system_interface_preferences` (
  `id` TINYINT UNSIGNED NOT NULL COMMENT '固定主键，仅允许 1',
  `vitality_theme_color` CHAR(7) NOT NULL DEFAULT '#3F6FAF' COMMENT '系统活力主题色，格式 #RRGGBB',
  `calm_theme_color` CHAR(7) NOT NULL DEFAULT '#355F63' COMMENT '系统沉稳主题色，格式 #RRGGBB',
  `updated_by` VARCHAR(64) NULL COMMENT '最后修改管理员用户 ID',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  CONSTRAINT `chk_system_interface_preferences_singleton` CHECK (`id` = 1),
  CONSTRAINT `chk_system_interface_vitality_theme_color` CHECK (BINARY `vitality_theme_color` REGEXP '^#[0-9A-F]{6}$'),
  CONSTRAINT `chk_system_interface_calm_theme_color` CHECK (BINARY `calm_theme_color` REGEXP '^#[0-9A-F]{6}$')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='系统界面偏好表：保存全局纯色主题配置。';
