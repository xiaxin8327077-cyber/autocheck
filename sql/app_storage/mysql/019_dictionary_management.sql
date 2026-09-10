SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `auto_check`;

CREATE TABLE IF NOT EXISTS `system_dictionaries` (
  `dictionary_code` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '字典分类编码',
  `dictionary_name` VARCHAR(100) NOT NULL COMMENT '字典分类名称',
  `description` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '分类说明',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `system_locked` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '系统锁定分类不可删除改码',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序值',
  `created_by` VARCHAR(64) NULL COMMENT '创建人',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  `updated_by` VARCHAR(64) NULL COMMENT '更新人',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`dictionary_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='系统字典分类';

CREATE TABLE IF NOT EXISTS `system_dictionary_items` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '字典项自增标识',
  `dictionary_code` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '所属字典分类编码',
  `item_code` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '字典项编码',
  `item_name` VARCHAR(100) NOT NULL COMMENT '字典项名称',
  `description` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '字典项说明',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
  `sort_order` INT NOT NULL DEFAULT 0 COMMENT '排序值',
  `created_by` VARCHAR(64) NULL COMMENT '创建人',
  `created_at` DATETIME(6) NOT NULL COMMENT '创建时间',
  `updated_by` VARCHAR(64) NULL COMMENT '更新人',
  `updated_at` DATETIME(6) NOT NULL COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_system_dictionary_items_code` (`dictionary_code`, `item_code`),
  KEY `ix_system_dictionary_items_list` (`dictionary_code`, `enabled`, `sort_order`, `id`),
  CONSTRAINT `fk_system_dictionary_items_dictionary`
    FOREIGN KEY (`dictionary_code`) REFERENCES `system_dictionaries` (`dictionary_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='系统字典项';

INSERT INTO `system_dictionaries` (
  `dictionary_code`, `dictionary_name`, `description`,
  `enabled`, `system_locked`, `sort_order`,
  `created_by`, `created_at`, `updated_by`, `updated_at`
) VALUES (
  'business_system', '业务系统', '报表特殊处理等功能使用的所属业务系统',
  1, 1, 10,
  'system', CURRENT_TIMESTAMP(6), 'system', CURRENT_TIMESTAMP(6)
) ON DUPLICATE KEY UPDATE `dictionary_code` = `dictionary_code`;
