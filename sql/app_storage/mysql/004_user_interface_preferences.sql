CREATE TABLE IF NOT EXISTS `user_interface_preferences` (
  `user_id` VARCHAR(64) NOT NULL COMMENT '用户 ID',
  `radius_px` TINYINT UNSIGNED NOT NULL DEFAULT 4 COMMENT '界面圆角像素值，范围 1 至 15',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`user_id`),
  CONSTRAINT `chk_user_interface_radius_px` CHECK (`radius_px` BETWEEN 1 AND 15)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户界面偏好表：保存每个用户的界面圆角设置。';
