SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

CREATE TABLE IF NOT EXISTS `system_notifications` (
  `id` CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '通知唯一标识',
  `source_module` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '来源模块标识',
  `event_type` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '来源事件类型',
  `category` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '通知展示分类',
  `level` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '通知级别',
  `title` VARCHAR(191) NOT NULL COMMENT '通知标题',
  `content` TEXT NOT NULL COMMENT '通知正文',
  `action_json` JSON NULL COMMENT '受控内部跳转描述',
  `dedupe_key` VARCHAR(191) NOT NULL COMMENT '原始业务去重键',
  `dedupe_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '去重键哈希',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  `expires_at` DATETIME(6) NOT NULL COMMENT '过期时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_system_notifications_source_event`
    (`source_module`, `event_type`, `dedupe_hash`),
  KEY `ix_system_notifications_expires` (`expires_at`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='通用系统通知主体';

CREATE TABLE IF NOT EXISTS `system_notification_recipients` (
  `notification_id` CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '通知标识',
  `user_id` VARCHAR(64) NOT NULL COMMENT '接收用户标识',
  `received_at` DATETIME(6) NOT NULL COMMENT '收件时间',
  `read_at` DATETIME(6) NULL COMMENT '已读时间',
  `cleared_at` DATETIME(6) NULL COMMENT '清空时间',
  PRIMARY KEY (`notification_id`, `user_id`),
  KEY `ix_system_notification_recipients_user_list`
    (`user_id`, `received_at`, `notification_id`),
  KEY `ix_system_notification_recipients_user_unread`
    (`user_id`, `read_at`, `received_at`),
  KEY `ix_system_notification_recipients_user_cleared`
    (`user_id`, `cleared_at`),
  CONSTRAINT `fk_system_notification_recipients_notification`
    FOREIGN KEY (`notification_id`) REFERENCES `system_notifications` (`id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='系统通知用户收件与已读状态';
